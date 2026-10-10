# Setup

1. Create a **public** repo named exactly `ynahmany` (same as your username) and push these files to `main`.
2. Create a token: GitHub → Settings → Developer settings → Personal access tokens → **Tokens (classic)** →
   scopes `repo` and `read:user` (or `read:org` too if you want org repos counted).
3. In the `ynahmany` repo: Settings → Secrets and variables → Actions → New repository secret
   → name `ACCESS_TOKEN`, value = the token.
4. Actions tab → "Update profile card" → **Run workflow**. The first run scans every repo for
   lines of code and can take a while; later runs only rescan repos with new commits.

## Customising
- Text on the card: edit `CONFIG` at the top of `today.py`.
- Show your age as "Uptime": set `"birthday": "YYYY-MM-DD"` in `CONFIG`.
- New portrait: `pip install rembg pillow opencv-python-headless`, `rembg i photo.jpg me.png`, then `python ascii_art.py me.png`
  (writes `ascii_dark.txt` + `ascii_light.txt`; try `--cols 38..48`).
- Preview locally without a token: `python today.py --demo`.
