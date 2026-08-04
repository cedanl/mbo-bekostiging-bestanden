"""Capture animated GIFs of the Streamlit app per feature, using Playwright + ffmpeg."""

import asyncio
import os
import subprocess
import sys
import time
from pathlib import Path

from playwright.async_api import async_playwright

FFMPEG = "/workspaces/dev-dots/savvy/app/node_modules/ffmpeg-static/ffmpeg"
BASE_URL = "http://localhost:8501"
ROOT = Path(__file__).parent.parent
ASSETS = ROOT / "docs" / "assets"
ASSETS.mkdir(parents=True, exist_ok=True)

# Each GIF spec: (name, list of (label, duration_seconds, action_fn))
# action_fn receives (page,) and is called before the screenshot is taken.


async def wait_streamlit(page):
    """Wait until Streamlit has finished its initial render."""
    await page.wait_for_selector("[data-testid='stApp']", timeout=30_000)
    await page.wait_for_load_state("networkidle", timeout=30_000)
    await asyncio.sleep(1.5)


async def scroll_to(page, selector):
    el = page.locator(selector).first
    await el.scroll_into_view_if_needed()
    await asyncio.sleep(0.4)


async def click_tab(page, label):
    tab = page.locator(f"button[role='tab']:has-text('{label}')")
    await tab.wait_for(state="visible", timeout=15_000)
    await tab.click()
    # Wacht tot de tab content geladen is (networkidle of minimaal 1.5s)
    try:
        await page.wait_for_load_state("networkidle", timeout=8_000)
    except Exception:
        pass
    await asyncio.sleep(1.5)


# ---------------------------------------------------------------------------
# GIF 1 — Home: bestanden ontdekken + verwerken
# ---------------------------------------------------------------------------

async def capture_home(page, tmp: Path) -> list[tuple[Path, float]]:
    frames: list[tuple[Path, float]] = []

    await page.goto(BASE_URL, wait_until="networkidle")
    await wait_streamlit(page)
    await asyncio.sleep(1)

    # Frame 1: hero + bestanden gevonden
    p = tmp / "home_00.png"
    await page.screenshot(path=str(p), full_page=False)
    frames.append((p, 2.5))

    # Frame 2: open eerste expander
    expanders = page.locator("[data-testid='stExpander'] summary")
    if await expanders.count() > 0:
        await expanders.first.click()
        await asyncio.sleep(0.8)
    p = tmp / "home_01.png"
    await page.screenshot(path=str(p), full_page=False)
    frames.append((p, 2.0))

    # Frame 3: scroll naar knop
    btn = page.locator("button:has-text('Verwerk alles')").first
    await btn.scroll_into_view_if_needed()
    await asyncio.sleep(0.5)
    p = tmp / "home_02.png"
    await page.screenshot(path=str(p), full_page=False)
    frames.append((p, 2.0))

    # Frame 4: klik verwerken + wacht op voortgang
    await btn.click()
    await asyncio.sleep(2.0)
    p = tmp / "home_03.png"
    await page.screenshot(path=str(p), full_page=False)
    frames.append((p, 2.0))

    # Frame 5: wacht op success en toon metrics
    await page.wait_for_selector("text=Verwerkt", timeout=120_000)
    await asyncio.sleep(1.5)
    p = tmp / "home_04.png"
    await page.screenshot(path=str(p), full_page=False)
    frames.append((p, 3.5))

    return frames


# ---------------------------------------------------------------------------
# GIF 2 — Dashboard: tabs doorlopen
# ---------------------------------------------------------------------------

async def capture_dashboard(page, tmp: Path) -> list[tuple[Path, float]]:
    frames: list[tuple[Path, float]] = []

    await page.goto(f"{BASE_URL}/dashboard", wait_until="networkidle")
    await wait_streamlit(page)
    # Wacht tot tabs zichtbaar zijn
    await page.wait_for_selector("button[role='tab']", timeout=20_000)
    await asyncio.sleep(1)

    # Frame 1: header metrics (bovenkant pagina)
    await page.evaluate("window.scrollTo(0, 0)")
    await asyncio.sleep(0.5)
    p = tmp / "dash_00.png"
    await page.screenshot(path=str(p), full_page=False)
    frames.append((p, 2.5))

    for i, tab in enumerate(["Rendementen", "Bekostiging", "Opleidingen", "Studenten", "Examens"], 1):
        await click_tab(page, tab)
        # Scroll naar tab-content zodat grafieken/tabellen zichtbaar zijn
        await page.evaluate("window.scrollTo(0, 300)")
        await asyncio.sleep(0.8)
        p = tmp / f"dash_{i:02d}.png"
        await page.screenshot(path=str(p), full_page=False)
        frames.append((p, 2.5))

    return frames


# ---------------------------------------------------------------------------
# GIF 3 — Resultaten: tabel selecteren + preview + download
# ---------------------------------------------------------------------------

async def capture_resultaten(page, tmp: Path) -> list[tuple[Path, float]]:
    frames: list[tuple[Path, float]] = []

    # Navigeer via de sidebar-link naar Home (behoudt WebSocket-sessie + session_state)
    home_link = page.locator("[data-testid='stSidebarNavLink']:has-text('Home'), a:has-text('Home')")
    await home_link.first.wait_for(state="visible", timeout=10_000)
    await home_link.first.click()
    await wait_streamlit(page)
    await asyncio.sleep(1)

    # Controleer of de done-state actief is; zo niet: verwerk opnieuw
    bekijk_btn = page.locator("button:has-text('Bekijk resultaten')")
    if await bekijk_btn.count() == 0:
        verwerk_btn = page.locator("button:has-text('Verwerk alles')")
        if await verwerk_btn.count() > 0:
            await verwerk_btn.first.click()
            await page.wait_for_selector("text=Verwerkt", timeout=120_000)
            await asyncio.sleep(1.5)

    # Klik "Bekijk resultaten →" — zet resultaten_dir in session_state + navigeert
    await bekijk_btn.first.wait_for(state="visible", timeout=10_000)
    await bekijk_btn.first.click()
    await wait_streamlit(page)
    await asyncio.sleep(1)

    # Frame 1: tabel-selectie (obt_inschrijvingen standaard geselecteerd)
    p = tmp / "res_00.png"
    await page.screenshot(path=str(p), full_page=False)
    frames.append((p, 2.5))

    # Frame 2: open selectbox — laat de dropdown met alle tabellen zien
    selectbox = page.locator("[data-testid='stSelectbox']").first
    await selectbox.wait_for(state="visible", timeout=10_000)
    await selectbox.scroll_into_view_if_needed()
    await selectbox.click()
    await asyncio.sleep(0.8)
    p = tmp / "res_01.png"
    await page.screenshot(path=str(p), full_page=False)
    frames.append((p, 2.0))

    # Kies detail_bekostiging
    opt = page.locator("li[role='option']").filter(has_text="detail_bekostiging")
    if await opt.count() > 0:
        await opt.first.click()
        await asyncio.sleep(1.5)
    else:
        await page.keyboard.press("Escape")
        await asyncio.sleep(0.5)

    # Frame 3: data tabel preview
    p = tmp / "res_02.png"
    await page.screenshot(path=str(p), full_page=False)
    frames.append((p, 2.5))

    # Frame 4: scroll naar download knop
    dl = page.locator("[data-testid='stDownloadButton']").first
    await dl.scroll_into_view_if_needed()
    await asyncio.sleep(0.5)
    p = tmp / "res_03.png"
    await page.screenshot(path=str(p), full_page=False)
    frames.append((p, 2.5))

    return frames


# ---------------------------------------------------------------------------
# ffmpeg: frames → GIF via palette
# ---------------------------------------------------------------------------

def make_gif(frames: list[tuple[Path, float]], output: Path, width: int = 960):
    """Gebruik ffmpeg concat-demuxer + palettegen voor een scherpe GIF."""
    tmp_dir = frames[0][0].parent

    # Schrijf concat-manifest
    concat = tmp_dir / "concat.txt"
    with concat.open("w") as f:
        for path, dur in frames:
            f.write(f"file '{path.name}'\n")
            f.write(f"duration {dur}\n")
        # Laatste frame herhalen (ffmpeg vereist dit voor concat)
        f.write(f"file '{frames[-1][0].name}'\n")

    palette = tmp_dir / "palette.png"

    # Stap 1: palettegen
    subprocess.run(
        [
            FFMPEG, "-y",
            "-f", "concat", "-safe", "0", "-i", str(concat),
            "-vf", f"scale={width}:-1:flags=lanczos,palettegen=stats_mode=diff",
            str(palette),
        ],
        check=True, capture_output=True,
    )

    # Stap 2: GIF
    subprocess.run(
        [
            FFMPEG, "-y",
            "-f", "concat", "-safe", "0", "-i", str(concat),
            "-i", str(palette),
            "-lavfi", f"scale={width}:-1:flags=lanczos[s];[s][1:v]paletteuse=dither=bayer",
            str(output),
        ],
        check=True, capture_output=True,
    )
    print(f"  ✓ {output.name}  ({output.stat().st_size // 1024} KB)")


# ---------------------------------------------------------------------------
# Main
# ---------------------------------------------------------------------------

async def main():
    import tempfile

    print("Starten van Playwright…")
    async with async_playwright() as pw:
        browser = await pw.chromium.launch(
            headless=True,
            args=["--no-sandbox", "--disable-dev-shm-usage"],
        )
        context = await browser.new_context(
            viewport={"width": 1280, "height": 800},
            device_scale_factor=1.5,
        )
        page = await context.new_page()

        with tempfile.TemporaryDirectory() as tmpdir:
            tmp = Path(tmpdir)

            print("\n[1/3] Home GIF…")
            home_frames = await capture_home(page, tmp)
            make_gif(home_frames, ASSETS / "home.gif")

            print("\n[2/3] Dashboard GIF…")
            dash_frames = await capture_dashboard(page, tmp)
            make_gif(dash_frames, ASSETS / "dashboard.gif")

            print("\n[3/3] Resultaten GIF…")
            res_frames = await capture_resultaten(page, tmp)
            make_gif(res_frames, ASSETS / "resultaten.gif")

        await browser.close()

    print("\nKlaar! GIFs in docs/assets/:")
    for gif in sorted(ASSETS.glob("*.gif")):
        print(f"  {gif.name}  {gif.stat().st_size // 1024} KB")


if __name__ == "__main__":
    asyncio.run(main())
