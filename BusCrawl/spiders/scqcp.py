# -*- coding: utf-8 -*-
import scrapy
import json
import datetime

from BusCrawl.items.scqcp import StartCityItem, TargetCityItem, LineItem


class ScqcpSpider(scrapy.Spider):
    name = "scqcp"
    custom_settings = {
        "ITEM_PIPELINES": {
            'BusCrawl.pipelines.scqcp.MongoPipeline': 300,
        },

        "DOWNLOADER_MIDDLEWARES": {
            'scrapy.contrib.downloadermiddleware.useragent.UserAgentMiddleware': None,
            'BusCrawl.middlewares.common.MobileRandomUserAgentMiddleware': 400,
            'BusCrawl.middlewares.common.ProxyMiddleware': 410,
            'BusCrawl.middlewares.scqcp.HeaderMiddleware': 410,
        }
    }

    def start_requests(self):
        url = "http://java.cdqcp.com/scqcp/api/v2/ticket/get_start_city"
        return [scrapy.FormRequest(url, formdata={'city_name': ''}, callback=self.parse_start_city)]

    def parse_start_city(self, response):
        "解析出发城市"
        res = json.loads(response.body)
        if int(res["status"]) != 1:
            self.logger.error("parse_start_city: Unexpected return, %s" % str(res))
            return

        url = "http://java.cdqcp.com/scqcp/api/v2/ticket/query_target_station_by_keyword"
        for d in res["start_city"]:
            yield StartCityItem(**d)
            fd = {
                "city_id": unicode(d["city_id"]),
                "city_name": unicode(d["city_name"]),
                "stop_name": "",
            }
            yield scrapy.FormRequest(url, formdata=fd, callback=self.parse_target_city, meta={"start": d})

    def parse_target_city(self, response):
        "解析目的地城市"
        res = json.loads(response.body)
        if int(res["status"]) != 1:
            self.logger.error("parse_target_city: Unexpected return, %s" % str(res))
            return

        url = "http://java.cdqcp.com/scqcp/api/v2/ticket/query"
        start = response.meta["start"]
        for d in res["target_city"]:
            yield TargetCityItem(**d)

            # 预售期5天, 节假日预售期10天
            today = datetime.date.today()
            for i in range(0, 5):
                sdate = str(today+datetime.timedelta(days=i))
                fd = {
                    "city_id": unicode(start["city_id"]),
                    "city_name": start["city_name"],
                    "riding_date": sdate,
                    "stop_name": d["stop_name"],
                }
                yield scrapy.FormRequest(url, formdata=fd, callback=self.parse_line, meta={"start": start, "end": d})

    def parse_line(self, response):
        "解析班车"
        res = json.loads(response.body)
        if int(res["status"]) != 1:
            self.logger.error("parse_line: Unexpected return, %s" % str(res))
            return
        for d in res["ticket_lines_query"]:
            yield LineItem(**d)