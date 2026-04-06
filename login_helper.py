#!/usr/bin/env python3
"""登录助手 - 手动登录并保存浏览器状态

使用方法：
    python login_helper.py

功能：
    1. 打开浏览器进行手动登录
    2. 保存登录状态（Cookies、LocalStorage）
    3. 后续爬虫自动加载已保存的登录状态

支持网站：
    - 智联招聘 (zhilian)
    - 前程无忧 (51job)
    - Boss直聘 (boss)
"""

import asyncio
import json
from pathlib import Path
from rich.console import Console
from rich.prompt import Prompt
from rich.table import Table

console = Console()

# 浏览器状态存储路径
STATE_DIR = Path("data/browser_state")


async def login_site(site_name: str, login_url: str, state_file: Path):
    """通用登录流程"""
    console.print(f"\n[bold cyan]{site_name}登录助手[/bold cyan]")
    console.print("=" * 50)
    console.print("\n[yellow]步骤说明：[/yellow]")
    console.print("1. 浏览器将自动打开登录页")
    console.print("2. 请完成登录（扫码/账号密码）")
    console.print("3. 如有验证码，请完成验证")
    console.print("4. 登录成功后，回到此窗口按 Enter 保存状态")
    console.print("\n[dim]提示：登录状态有效期为几天到几周不等[/dim]")

    Prompt.ask("\n按 Enter 开始登录", default="")

    from playwright.async_api import async_playwright

    async with async_playwright() as p:
        browser = await p.chromium.launch(
            headless=False,  # 显示浏览器
            args=[
                "--disable-blink-features=AutomationControlled",
                "--start-maximized",
                "--no-sandbox",
            ],
        )

        context = await browser.new_context(
            viewport={"width": 1920, "height": 1080},
            locale="zh-CN",
            timezone_id="Asia/Shanghai",
            user_agent="Mozilla/5.0 (Windows NT 10.0; Win64; x64) AppleWebKit/537.36 (KHTML, like Gecko) Chrome/120.0.0.0 Safari/537.36",
        )

        page = await context.new_page()

        # 注入反检测脚本
        await page.add_init_script("""
            Object.defineProperty(navigator, 'webdriver', { get: () => undefined });
            Object.defineProperty(navigator, 'plugins', { get: () => [1, 2, 3, 4, 5] });
            window.chrome = { runtime: {} };
        """)

        # 访问登录页
        await page.goto(login_url, wait_until="domcontentloaded")

        console.print("\n[yellow]等待登录...[/yellow]")
        console.print("[dim]请在浏览器中完成登录操作[/dim]")
        Prompt.ask("登录完成后按 Enter 保存状态", default="")

        # 保存状态
        STATE_DIR.mkdir(parents=True, exist_ok=True)
        await context.storage_state(path=str(state_file))

        console.print(f"\n[green]✓ 登录状态已保存到: {state_file}[/green]")

        await browser.close()


def check_login_status():
    """检查已保存的登录状态"""
    console.print("\n[bold cyan]已保存的登录状态[/bold cyan]")
    console.print("=" * 50)

    if not STATE_DIR.exists():
        console.print("[yellow]尚未保存任何登录状态[/yellow]")
        console.print("\n运行 'python login_helper.py' 进行登录")
        return

    table = Table(show_header=True, header_style="bold")
    table.add_column("网站", style="cyan")
    table.add_column("状态", style="green")
    table.add_column("Cookies 数量")
    table.add_column("保存路径")

    has_valid = False
    for state_file in sorted(STATE_DIR.glob("*.json")):
        site = state_file.stem.replace("_state", "")

        try:
            with open(state_file, encoding="utf-8") as f:
                state = json.load(f)

            cookies = state.get("cookies", [])
            cookie_count = len(cookies)

            if cookie_count > 0:
                table.add_row(site, "✓ 有效", str(cookie_count), str(state_file))
                has_valid = True
            else:
                table.add_row(site, "? 无效", "0", str(state_file))
        except Exception as e:
            table.add_row(site, "✗ 错误", "-", str(state_file))

    console.print(table)

    if has_valid:
        console.print("\n[green]可以使用已保存的登录状态进行爬取[/green]")
    else:
        console.print("\n[yellow]没有有效的登录状态，请先登录[/yellow]")


def main():
    # 网站配置
    SITES = {
        "1": ("智联招聘", "https://passport.zhaopin.com/login", STATE_DIR / "zhilian_state.json"),
        "2": ("前程无忧", "https://login.51job.com/login.php", STATE_DIR / "51job_state.json"),
        "3": ("Boss直聘", "https://www.zhipin.com/web/user/?ka=header-login", STATE_DIR / "boss_state.json"),
    }

    console.print("\n[bold]═══════════════════════════════════════[/bold]")
    console.print("[bold]       招聘网站登录助手[/bold]")
    console.print("[bold]═══════════════════════════════════════[/bold]")

    console.print("\n[cyan]选项菜单：[/cyan]")
    console.print("  [1] 智联招聘登录")
    console.print("  [2] 前程无忧登录")
    console.print("  [3] Boss直聘登录")
    console.print("  [4] 查看已保存的登录状态")
    console.print("  [0] 退出")

    choice = Prompt.ask("\n请选择", choices=["0", "1", "2", "3", "4"], default="0")

    if choice == "0":
        console.print("\n[dim]再见！[/dim]")
    elif choice == "4":
        check_login_status()
    elif choice in SITES:
        name, url, file = SITES[choice]
        asyncio.run(login_site(name, url, file))
        # 登录后显示状态
        check_login_status()
    else:
        console.print("[red]无效选择[/red]")


if __name__ == "__main__":
    main()
