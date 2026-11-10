"""Capture first three raw public World Class trainer API records via browser session.
Python 3.10+, Playwright. Does not modify collector CSV/SQLite/PostgreSQL.
"""
import argparse
import json
from pathlib import Path
from datetime import datetime, timezone
from playwright.sync_api import sync_playwright

START_URL = "https://www.worldclass.ru/trainers/"
API_URL = "https://www.worldclass.ru/api/trainers"

PARAMS = {
    "pagination[page]": "1",
    "pagination[pageSize]": "12",
    "populate[0]": "club",
    "populate[1]": "additional_image",
    "populate[2]": "grade",
    "populate[3]": "gender",
    "filters[training_categories][service_type][$eq]": "fitness",
}


def main():
    parser = argparse.ArgumentParser(description="Save first three raw World Class API trainer records")
    parser.add_argument("--output", default="worldclass_api_sample.json")
    parser.add_argument("--headless", action="store_true", help="Run browser without visible window")
    args = parser.parse_args()

    output = Path(args.output).resolve()
    with sync_playwright() as playwright:
        browser = playwright.chromium.launch(headless=args.headless)
        context = browser.new_context(locale="ru-RU", viewport={"width": 1400, "height": 900})
        page = context.new_page()
        try:
            response = page.goto(START_URL, wait_until="domcontentloaded", timeout=60000)
            print(f"Каталог открыт: HTTP {response.status if response else 'no response'}")
            result = page.evaluate(
                """async ({apiUrl, params}) => {
                    const query = new URLSearchParams(params);
                    const response = await fetch(apiUrl + '?' + query.toString(), {
                        method: 'GET',
                        credentials: 'same-origin',
                        headers: {'Accept': 'application/json'}
                    });
                    const text = await response.text();
                    let payload = null;
                    try { payload = JSON.parse(text); } catch (_) {}
                    return {
                        http_status: response.status,
                        content_type: response.headers.get('content-type'),
                        payload,
                        response_preview: payload ? null : text.slice(0, 1500)
                    };
                }""",
                {"apiUrl": API_URL, "params": PARAMS},
            )
            if result["http_status"] != 200:
                raise RuntimeError(
                    f"API вернул HTTP {result['http_status']}. "
                    f"Фрагмент ответа: {result.get('response_preview')}"
                )
            payload = result.get("payload")
            if not isinstance(payload, dict) or not isinstance(payload.get("data"), list):
                raise RuntimeError("Ответ HTTP 200 не содержит ожидаемый массив data")

            records = payload["data"][:3]
            if not records:
                raise RuntimeError("API вернул пустой массив data")

            document = {
                "captured_at": datetime.now(timezone.utc).isoformat(),
                "source": API_URL,
                "request": {"method": "GET", "params": PARAMS},
                "http_status": result["http_status"],
                "content_type": result.get("content_type"),
                "pagination": (payload.get("meta") or {}).get("pagination"),
                "record_count_in_response": len(payload["data"]),
                "sample_record_count": len(records),
                "records": records,
            }
            output.write_text(json.dumps(document, ensure_ascii=False, indent=2), encoding="utf-8")
            print(f"Сохранено исходных JSON-записей: {len(records)}")
            print(f"Параметры пагинации: {document['pagination']}")
            print(f"Файл: {output}")
            print("CSV, SQLite и PostgreSQL не изменялись.")
        finally:
            context.close()
            browser.close()


if __name__ == "__main__":
    main()
