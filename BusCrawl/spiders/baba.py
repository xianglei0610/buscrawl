#!/usr/bin/env python
# encoding: utf-8

import scrapy
import json
import datetime

from datetime import datetime as dte
from BusCrawl.item import LineItem
from base import SpiderBase
from BusCrawl.utils.tool import get_pinyin_first_litter

PROVINCE_TO_CITY = {
    "浙江": [],
    "江苏": ["宿迁", "镇江", "常州", "南通", "苏州", "徐州", "连云港", "淮安", "泰州", "无锡", "南京"],
    "安徽": ["宁国", "滁州", "安庆", "明光", "全椒", "天长", "歙县"],
}

CITY_TO_PROVINCE = {}
for p, vlst in PROVINCE_TO_CITY.items():
    for c in vlst:
        CITY_TO_PROVINCE[unicode(c)] = unicode(p)
del p, vlst


class BabaSpider(SpiderBase):
    name = "baba"
    custom_settings = {
        "ITEM_PIPELINES": {
            'BusCrawl.pipeline.MongoPipeline': 300,
        },

        "DOWNLOADER_MIDDLEWARES": {
            'scrapy.contrib.downloadermiddleware.useragent.UserAgentMiddleware': None,
            'BusCrawl.middleware.MobileRandomUserAgentMiddleware': 400,
            'BusCrawl.middleware.ProxyMiddleware': 410,
            'BusCrawl.middleware.BabaHeaderMiddleware': 410,
        },
    }

    def post_data_templ(self, content):
        tmpl = {
            "content": content,
            "common": {
                "pushToken": "864895020513527",
                "channelVer": "BabaBus",
                "usId": "",
                "appId": "com.hundsun.InternetSaleTicket",
                "appVer": "1.3.0",
                "loginStatus": "0",
                "imei": "864895020513527",
                "mobileVer": "6.0",
                "terminalType": "1",
                "platformCode": "01",
            },
            "key": ""
        }
        return tmpl

    def start_requests(self):
        start_url = "http://s4mdata.bababus.com:80/app/v4/ticket/cityAllListFrom.htm"
        content = {"dataVersion": ""}
        fd = self.post_data_templ(content)
        yield scrapy.Request(start_url,
                             method="POST",
                             body=json.dumps(fd),
                             callback=self.parse_start_city)

    def get_dest_list(self, province, city):
        dest_url = "http://s4mdata.bababus.com:80/app/v3/ticket/getStationList.htm"
        dest_list = []
        for c in [chr(i) for i in range(97, 123)]:
            content = {"searchType": "1", "dataName": c, "beginCityName": city}
            fd = self.post_data_templ(content)

            ua = "Mozilla/5.0 (Linux; U; Android 2.2; fr-lu; HTC Legend Build/FRF91) AppleWebKit/533.1 (KHTML, like Gecko)  Version/4.0 Mobile Safari/533.1"
            headers = {"User-Agent": ua}
            import requests
            r = requests.post(dest_url, data=json.dumps(fd), headers=headers)
            res = r.json()
            dest_list.extend(res["content"]["toStationList"])
        return dest_list

    def parse_start_city(self, response):
        res = json.loads(response.body)
        if res["returnNo"] != "0000":
            self.logger.error("parse_start_city: Unexpected return, %s", res)
            return
        line_url = "http://s4mdata.bababus.com:80/app/v4/ticket/busList.htm"
        for info in res["content"]["cityList"]:
            name = info["cityName"]
            if not self.is_need_crawl(city=name):
                continue
            if name not in CITY_TO_PROVINCE:
                continue
            province = CITY_TO_PROVINCE[name]
            start = {
                "province": province,
                "city_name": info["cityName"],
                "city_code": info["allSpell"],
                "city_id": info["cityId"],
            }
            for info in self.get_dest_list(province, name):
                end = {
                    "city_name": info["stationName"],
                    "city_code": get_pinyin_first_litter(info["stationName"]),
                    "city_id": info["stationId"],
                }
                self.logger.info("start %s ==> %s" % (start["city_name"], end["city_name"]))
                today = datetime.date.today()
                for i in range(self.start_day(), 8):
                    sdate = str(today + datetime.timedelta(days=i))
                    if self.has_done(start["city_name"], end["city_name"], sdate):
                        continue
                    content = {
                        "pageSize": 1025,
                        "beginCityName": start["city_name"],
                        "currentPage": 1,
                        "endCityName": end["city_name"],
                        "leaveDate": sdate,
                        "beginCityId": start["city_id"],
                        "endCityId": end["city_id"],
                    }
                    fd = self.post_data_templ(content)
                    yield scrapy.Request(line_url,
                                         method="POST",
                                         body=json.dumps(fd),
                                         callback=self.parse_line,
                                         meta={"start": start, "end": end, "date": sdate})

    def parse_line(self, response):
        "解析班车"
        start = response.meta["start"]
        end = response.meta["end"]
        sdate = response.meta["date"]
        self.mark_done(start["city_name"], end["city_name"], sdate)
        try:
            res = json.loads(response.body)
        except Exception, e:
            raise e
        if res["returnNo"] != "0000":
            #self.logger.error("parse_line: Unexpected return, %s, %s->%s, %s", sdate, start["city_name"], end["city_name"], res["header"])
            return
        for d in res["content"]["busList"]:
            attrs = dict(
                s_province = start["province"],
                s_city_name = start["city_name"],
                s_city_id = start["city_id"],
                s_city_code=start["city_code"],
                s_sta_name = d["beginStation"],
                s_sta_id = d["beginStationId"],
                d_city_name = end["city_name"],
                d_city_code=end["city_code"],
                d_city_id = end["city_id"],
                d_sta_name = d["endStation"],
                d_sta_id = d["endStationId"],
                drv_date = d["leaveDate"],
                drv_time = d["leaveTime"],
                drv_datetime = dte.strptime("%s %s" % (d["leaveDate"], d["leaveTime"]), "%Y-%m-%d %H:%M"),
                distance = "0",
                vehicle_type = d["busType"],
                seat_type = "",
                bus_num = d["busId"],
                full_price = float(d["fullPrice"]),
                half_price = float(d["fullPrice"])/2,
                fee = 0,
                crawl_datetime = dte.now(),
                extra_info = {"depotName": d["depotName"], "sbId": d["sbId"], "stId": d["stId"], "depotId": d["depotId"]},
                left_tickets = int(d["remainCount"]),
                crawl_source = "baba",
                shift_id="",
            )
            yield LineItem(**attrs)
