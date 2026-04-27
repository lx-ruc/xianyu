"""搜索闲鱼竞品商品 - API拦截 + DOM提取"""

import json
import os
import re
import sys
import time
from playwright.sync_api import sync_playwright


def search_competitors(keyword: str, max_pages: int = 3) -> list[dict]:
    """用 Playwright 搜索，同时拦截API和DOM"""
    results: list[dict] = []
    api_items: list[dict] = []  # 从API响应中获取的商品

    def on_response(response):
        url = response.url
        if "idlemtopsearch.pc.search" in url and "suggest" not in url and response.status == 200:
            try:
                body = response.json()
                data = body.get("data", {})
                items = data.get("items", [])
                if items:
                    api_items.append({"response": body, "url": url})
                    print(f"  [API] 拦截到 {len(items)} 个商品")
            except Exception:
                pass

    cookies_str = os.getenv("COOKIES_STR", "")

    with sync_playwright() as p:
        browser = p.chromium.launch(headless=False)
        context = browser.new_context(
            user_agent=(
                "Mozilla/5.0 (Macintosh; Intel Mac OS X 10_15_7) "
                "AppleWebKit/537.36 (KHTML, like Gecko) "
                "Chrome/131.0.0.0 Safari/537.36"
            )
        )

        if cookies_str:
            cookies_to_add = []
            for pair in cookies_str.split(";"):
                pair = pair.strip()
                if "=" in pair:
                    name, value = pair.split("=", 1)
                    cookies_to_add.append({
                        "name": name.strip(),
                        "value": value.strip(),
                        "domain": ".goofish.com",
                        "path": "/",
                    })
            if cookies_to_add:
                context.add_cookies(cookies_to_add)
                print(f"  已注入 {len(cookies_to_add)} 个cookie")

        page = context.new_page()
        page.on("response", on_response)

        search_url = f"https://www.goofish.com/search?q={keyword}"
        print(f"  正在打开: {search_url}")
        page.goto(search_url, wait_until="networkidle", timeout=30000)
        time.sleep(5)

        # 关闭弹窗
        for selector in [".ant-modal-close", "div[class*='closeIconBg']"]:
            try:
                el = page.locator(selector)
                if el.count() > 0:
                    el.first.click(timeout=1000)
                    time.sleep(0.3)
            except Exception:
                pass

        # 方法1: 从API响应中提取商品ID
        api_ids: dict[str, dict] = {}
        for entry in api_items:
            body = entry["response"]
            data = body.get("data", {})
            items = data.get("items", [])
            for item in items:
                try:
                    main_data = item.get("data", {}).get("item", {}).get("main", {})
                    ex = main_data.get("exContent", {})
                    target_url = main_data.get("targetUrl", "")
                    title = ex.get("title", "")
                    item_id = ""

                    if "id=" in target_url:
                        item_id = target_url.split("id=")[1].split("&")[0]
                    elif "/item/" in target_url:
                        item_id = target_url.split("/item/")[1].split("?")[0].split("/")[0]

                    if item_id and item_id not in api_ids:
                        price_parts = ex.get("price", [])
                        price_str = ""
                        for part in price_parts:
                            if isinstance(part, dict):
                                price_str += part.get("text", "")
                            elif isinstance(part, str):
                                price_str += part

                        api_ids[item_id] = {
                            "title": title,
                            "price": price_str,
                            "area": ex.get("area", ""),
                            "seller": ex.get("userNickName", ""),
                            "item_id": item_id,
                            "publish_time": main_data.get("clickParam", {})
                                .get("args", {}).get("publishTime", 0),
                        }
                except Exception:
                    continue

        print(f"  [API] 提取到 {len(api_ids)} 个有ID的商品")

        # 方法2: 从DOM提取
        dom_items = page.evaluate("""() => {
            const results = [];
            // 闲鱼搜索结果卡片是 a.feeds-item-wrap 标签
            const cards = document.querySelectorAll('a[class*="feeds-item-wrap"]');
            cards.forEach(card => {
                const titleEl = card.querySelector('[class*="main-title"]');
                const title = titleEl ? titleEl.textContent.trim() : '';
                const priceEl = card.querySelector('[class*="number--"]');
                const price = priceEl ? priceEl.textContent.trim() : '';
                const href = card.getAttribute('href') || '';
                if (title || href) {
                    results.push({ title, price: '¥' + price, href });
                }
            });
            return results;
        }""")

        # 方法3: 从页面所有a标签提取商品链接 (格式: /item?id=XXXXX)
        all_links = page.evaluate("""() => {
            const links = [];
            document.querySelectorAll('a[href*=\"item?id=\"], a[href*=\"/item?\"]').forEach(a => {
                const href = a.getAttribute('href') || '';
                links.push(href);
            });
            return [...new Set(links)];
        }""")
        print(f"  [DOM] 找到 {len(all_links)} 个商品链接")
        print(f"  [DOM] 找到 {len(dom_items)} 个商品卡片")

        # 合并数据：以API数据为基础，DOM数据补充
        # 先添加API数据
        for item_id, item_data in api_ids.items():
            results.append(item_data)

        # 从DOM链接提取ID补充 (格式: /item?id=XXXXX 或 /item/XXXXX)
        dom_ids: set[str] = set()
        for link in all_links:
            match = re.search(r'[?&]id=(\d+)', link) or re.search(r'/item/(\d+)', link)
            if match:
                dom_ids.add(match.group(1))

        # DOM有ID但API没有的
        for item_id in dom_ids:
            if item_id not in api_ids:
                # 在DOM数据中找对应标题
                title = ""
                price = ""
                for di in dom_items:
                    href = di.get("href", "")
                    if item_id in href:
                        title = di.get("title", "")
                        price = di.get("price", "")
                        break

                results.append({
                    "title": title,
                    "price": price,
                    "area": "",
                    "seller": "",
                    "item_id": item_id,
                    "publish_time": 0,
                })

        # DOM既没链接也没API数据的（纯文本提取）
        for di in dom_items:
            href = di.get("href", "")
            item_id_match = re.search(r'[?&]id=(\d+)', href) if href else None
            if not item_id_match and di.get("title"):
                results.append({
                    "title": di.get("title", ""),
                    "price": di.get("price", ""),
                    "area": "",
                    "seller": "",
                    "item_id": "",
                    "publish_time": 0,
                })

        print(f"  合计: {len(results)} 个商品 (有ID: {len([r for r in results if r.get('item_id')])})")

        browser.close()

    return results


def enrich_with_details(items: list[dict], api) -> list[dict]:
    """用详情API补充浏览量和想要数"""
    enriched = []
    for i, item in enumerate(items):
        item_id = item.get("item_id", "")
        if not item_id:
            enriched.append({**item, "browseCnt": None, "wantCnt": None})
            continue

        try:
            detail = api.get_item_info(item_id)
            data = detail.get("data", {})
            item_do = data.get("itemDO", {})
            title = item.get("title", "") or item_do.get("title", "")
            price = item.get("price", "")
            if not price:
                price = f"¥{item_do.get('price', '')}"

            enriched.append({
                **item,
                "title": title[:60],
                "price": price,
                "browseCnt": item_do.get("browseCnt", 0),
                "wantCnt": item_do.get("wantCnt", 0),
            })
            print(f"  [{i+1}/{len(items)}] {title[:30]}... 浏览:{item_do.get('browseCnt',0)} 想要:{item_do.get('wantCnt',0)}")
            time.sleep(0.3)
        except Exception as e:
            print(f"  [{i+1}/{len(items)}] 失败 {item_id}: {e}")
            enriched.append({**item, "browseCnt": None, "wantCnt": None})

    return enriched


def print_analysis(items: list[dict], keyword: str):
    """打印竞品分析报告"""
    print(f"\n{'='*70}")
    print(f"  闲鱼竞品分析报告 - 搜索词: 「{keyword}」")
    print(f"  共 {len(items)} 个竞品商品")
    print(f"{'='*70}\n")

    sorted_items = sorted(
        items, key=lambda x: x.get("browseCnt") or 0, reverse=True
    )

    for i, item in enumerate(sorted_items, 1):
        title = (item.get("title") or "")[:42]
        price = item.get("price", "")
        views = item.get("browseCnt", "N/A")
        wants = item.get("wantCnt", "N/A")
        item_id = item.get("item_id", "")

        # 清理价格文本
        price_clean = re.sub(r'(\d+人想要|累计降价.*|已降.*|)', '', price).strip()

        print(f"  [{i:2d}] {title}")
        print(f"       价格: {price_clean}  |  浏览: {views}  |  想要: {wants}")
        print()

    valid = [it for it in items if it.get("browseCnt") is not None]
    if valid:
        views_list = [it["browseCnt"] for it in valid]
        wants_list = [it["wantCnt"] for it in valid]

        print(f"{'='*70}")
        print(f"  数据汇总 ({len(valid)} 个有数据的商品):")
        print(f"  平均浏览量: {sum(views_list)/len(views_list):.0f}")
        print(f"  最高浏览量: {max(views_list)}")
        print(f"  最低浏览量: {min(views_list)}")
        print(f"  平均想要数: {sum(wants_list)/len(wants_list):.1f}")
        print(f"  最高想要数: {max(wants_list)}")
        print(f"{'='*70}")


if __name__ == "__main__":
    keyword = sys.argv[1] if len(sys.argv) > 1 else "考研数学辅导"
    max_pages = int(sys.argv[2]) if len(sys.argv) > 2 else 3

    from dotenv import load_dotenv
    load_dotenv()

    print(f"正在搜索: {keyword}...\n")

    items = search_competitors(keyword, max_pages)
    print(f"\n获取到 {len(items)} 个商品，正在获取详情...\n")

    try:
        sys.path.insert(0, "/Users/lixin/xianyu")
        from XianyuApis import XianyuApis
        from utils.xianyu_utils import trans_cookies

        cookies_str = os.getenv("COOKIES_STR", "")
        api = XianyuApis()
        api.session.cookies.update(trans_cookies(cookies_str))
        items = enrich_with_details(items, api)
    except Exception as e:
        print(f"详情API不可用 ({e})\n")

    print_analysis(items, keyword)

    output_file = f"/Users/lixin/xianyu/data/competitor_{keyword}.json"
    os.makedirs(os.path.dirname(output_file), exist_ok=True)
    with open(output_file, "w", encoding="utf-8") as f:
        json.dump(items, f, ensure_ascii=False, indent=2)
    print(f"\n数据已保存到: {output_file}")
