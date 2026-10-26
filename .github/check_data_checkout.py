"""避免 checkout 失敗後誤寫程式庫，或用空資料發布網站。"""
from pathlib import Path
import subprocess


def check(directory=Path("data")):
    directory = directory.resolve()
    top = subprocess.check_output(
        ["git", "-C", str(directory), "rev-parse", "--show-toplevel"], text=True
    ).strip()
    if Path(top).resolve() != directory:
        raise ValueError("data/ 必須是獨立的 Git checkout")
    remote = subprocess.check_output(
        ["git", "-C", str(directory), "remote", "get-url", "origin"], text=True
    ).strip().removesuffix(".git")
    if remote not in ("https://github.com/iPliny/ptt-iphone-data", "git@github.com:iPliny/ptt-iphone-data"):
        raise ValueError("data/ 的 origin 必須是指定的私人資料庫")
    for name in ("listings.csv", "events.csv", "jp/latest.csv", "jp/prices.csv"):
        file = directory / name
        if not file.is_file() or file.stat().st_size == 0:
            raise ValueError("私人資料庫缺少必要資料；停止抓取與部署")


if __name__ == "__main__":
    check()
    print("私人資料 checkout 檢查通過")
