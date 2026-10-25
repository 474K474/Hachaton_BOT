"""
python -m eventbot              — запустить бота с планировщиком
python -m eventbot collect      — один прогон парсеров, вывести найденное (без БД)
python -m eventbot collect --save — то же, но сохранить в БД
"""
import argparse
import asyncio
import logging

from eventbot.app import collect_cli, run_bot
from eventbot.config import get_settings


def main() -> None:
    parser = argparse.ArgumentParser(prog="eventbot")
    sub = parser.add_subparsers(dest="cmd")
    p_collect = sub.add_parser("collect", help="один прогон сбора")
    p_collect.add_argument("--save", action="store_true", help="сохранить в БД")
    args = parser.parse_args()

    logging.basicConfig(
        level=get_settings().log_level,
        format="%(asctime)s %(levelname)s %(name)s: %(message)s",
    )
    if args.cmd == "collect":
        asyncio.run(collect_cli(args.save))
    else:
        asyncio.run(run_bot())


if __name__ == "__main__":
    main()
