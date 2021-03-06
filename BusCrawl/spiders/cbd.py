#!/usr/bin/env python
# encoding: utf-8
import scrapy
import json
import datetime
import requests
import urllib

from datetime import datetime as dte
from BusCrawl.item import LineItem
from BusCrawl.utils.tool import md5, get_pinyin_first_litter
from base import SpiderBase

class CBDSpider(SpiderBase):
    name = "cbd"
    custom_settings = {
        "ITEM_PIPELINES": {
            'BusCrawl.pipeline.MongoPipeline': 300,
        },

        "DOWNLOADER_MIDDLEWARES": {
            'scrapy.contrib.downloadermiddleware.useragent.UserAgentMiddleware': None,
            'BusCrawl.middleware.MobileRandomUserAgentMiddleware': 400,
            'BusCrawl.middleware.ProxyMiddleware': 410,
            'BusCrawl.middleware.CbdHeaderMiddleware': 410,
        },
        #"DOWNLOAD_DELAY": 0.2,
        "RANDOMIZE_DOWNLOAD_DELAY": True,
    }

    def get_dest_list(self, province, city):
        url = "http://www.chebada.com/Home/GetBusDestinations"
        for city in [city, city+"市", city+"县", city.rstrip(u"市").rstrip("县")]:
            r = requests.post(url, headers={"User-Agent": "Chrome", "Content-Type": "application/x-www-form-urlencoded"}, data=urllib.urlencode({"departure": city}))
            lst = []
            temp = {}
            res = r.json()["response"]
            if "body" not in res:
                continue
            for d in res["body"]["destinationList"]:
                for c in d["cities"]:
                    if c["name"] in temp:
                        continue
                    temp[c["name"]] = 1
                    lst.append({"name": c["name"], "code": c["shortEnName"]})
            return lst

    def start_requests(self):
        # 这是个pc网页页面
        line_url = "http://m.chebada.com/Schedule/GetBusSchedules"
        start_list = [
            "苏州", "南京",
            "无锡", "常州",
            "南通", "张家港",
            "昆山", "吴江",
            "常熟", "太仓",
            "镇江", "宜兴",
            "江阴", "兴化",
            "盐城", "扬州",
            "连云港", "徐州",
            "宿迁",
            "淮安", "句容",
            "靖江", "大丰",
            "扬中", "溧阳",
            "射阳", "滨海",
            "盱眙", "涟水",
            "宝应", "丹阳",
            "海安", "海门",

            "金坛", "江都",
            "启东", "如皋",
            "如东", "泗阳",
            "沭阳", "泰兴",
            "仪征",
        ]
        for name in start_list:
            name = unicode(name)
            if not self.is_need_crawl(city=name):
                continue
            self.logger.info("start crawl city %s", name)
            start = {"name": name, "province": "江苏"}
            for s in self.get_dest_list(start["province"], start["name"]):
                name, code = s["name"], s["code"]
                end = {"name": name, "short_pinyin": code}

                today = datetime.date.today()
                for i in range(self.start_day(), 4):
                    sdate = str(today+datetime.timedelta(days=i))
                    if self.has_done(start["name"], end["name"], sdate):
                        self.logger.info("ignore %s ==> %s %s" % (start["name"], end["name"], sdate))
                        continue
                    params = dict(
                        departure=start["name"],
                        destination=end["name"],
                        departureDate=sdate,
                        page="1",
                        pageSize="1025",
                        hasCategory="true",
                        category="0",
                        dptTimeSpan="0",
                        bookingType="0",
                    )
                    yield scrapy.FormRequest(line_url, formdata=params, callback=self.parse_line, meta={"start": start, "end": end, "sdate": sdate})

    def parse_line(self, response):
        "解析班车"
        start = response.meta["start"]
        end= response.meta["end"]
        sdate = response.meta["sdate"]
        self.mark_done(start["name"], end["name"], sdate)
        self.logger.info("finish %s ==> %s" % (start["name"], end["name"]))
        try:
            res = json.loads(response.body)
        except Exception, e:
            print response.body
            raise e
        res = res["response"]
        if int(res["header"]["rspCode"]) != 0:
            #self.logger.error("parse_target_city: Unexpected return, %s" % res["header"])
            return

        for d in res["body"]["scheduleList"]:
            # if int(d["canBooking"]) != 1:
            #     continue
            left_tickets = int(d["ticketLeft"])
            from_city = unicode(d["departure"])
            to_city = unicode(d["destination"])
            from_station = unicode(d["dptStation"])
            to_station = unicode(d["arrStation"])

            attrs = dict(
                s_province = start["province"],
                s_city_id = "",
                s_city_name = from_city,
                s_sta_name = from_station,
                s_city_code=get_pinyin_first_litter(from_city),
                s_sta_id="",
                d_city_name = to_city,
                d_city_id="",
                d_city_code=end["short_pinyin"],
                d_sta_id="",
                d_sta_name = to_station,
                drv_date = d["dptDate"],
                drv_time = d["dptTime"],
                drv_datetime = dte.strptime("%s %s" % (d["dptDate"], d["dptTime"]), "%Y-%m-%d %H:%M"),
                distance = unicode(d["distance"]),
                vehicle_type = d["coachType"],
                seat_type = "",
                bus_num = d["coachNo"],
                full_price = float(d["ticketPrice"]),
                half_price = float(d["ticketPrice"])/2,
                fee = float(d["ticketFee"]),
                crawl_datetime = dte.now(),
                extra_info = {"raw_info": d},
                left_tickets = left_tickets,
                crawl_source = "cbd",
                shift_id="",
            )
            yield LineItem(**attrs)
