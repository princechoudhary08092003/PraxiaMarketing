# Moving Praxia to your own machine

The three Praxia apps are independent GitHub repos. Clone them **side by side** (as siblings in the
same folder) so the marketing app can find the website's logo/brand assets automatically.

```
your-folder/
  praxia-marketing/          # this repo  (PraxiaMarketing)  -> the Growth Studio, port 8020
  praxia-studios-website/    # PraxiaSite  -> logo + brand assets + the public site
  praxia-course-factory/     # PraxiaMainApp -> the course generator, ports 8010/5183
```

## 1. Install prerequisites (one time)
- **Python 3.11+** (tick "Add to PATH" on Windows), **Git**. (Node.js 18+ only if you also run the
  course-factory frontend.)

## 2. Clone the repos
```
git clone https://github.com/<your-account>/PraxiaMarketing.git    praxia-marketing
git clone https://github.com/<your-account>/PraxiaSite.git         praxia-studios-website
git clone https://github.com/<your-account>/PraxiaMainApp.git      praxia-course-factory
```
(If transferring GitHub ownership: on each repo, GitHub → Settings → Danger Zone → Transfer. Or just
re-push to a new account: `git remote set-url origin <new-url>` then `git push`.)

## 3. Run the marketing / Growth Studio app
Double-click **`praxia-marketing/start.bat`**. The first run creates its own virtual environment,
installs everything (including the headless browser for product screenshots), then opens
`http://127.0.0.1:8020`. Later runs just start it.

## 4. Add your keys — `praxia-marketing/backend/.env`
Secrets are NOT in git. Copy `backend/.env.example` to `backend/.env` (start.bat does this for you)
and fill in **your personal** accounts:

| Key | What / where to get it |
|---|---|
| `OPENAI_API_KEY` | platform.openai.com (scripts, voiceover, images) |
| `SMTP_USER` / `SMTP_APP_PASSWORD` | your Gmail + an App Password (for outreach + reply sync) |
| `IG_API=instagram`, `FB_APP_SECRET`, `IG_ACCESS_TOKEN` | Meta app (Instagram Login) -> then run `python -m app.setup_ig` to fill `IG_USER_ID` + long-lived token |
| `YT_CLIENT_ID` / `YT_CLIENT_SECRET` / `YT_REFRESH_TOKEN` | Google Cloud OAuth -> `python -m app.setup_youtube` |
| `CLOUDINARY_CLOUD_NAME` / `_API_KEY` / `_API_SECRET` | cloudinary.com (throwaway video pass-through for IG) |
| `PEXELS_API_KEY` | pexels.com/api (real stock photos) |

Run the helpers from `praxia-marketing/backend`:
```
.venv\Scripts\python -m app.setup_ig
.venv\Scripts\python -m app.setup_youtube
```

## 5. Notes
- **Brand assets:** with the website repo cloned as a sibling, the logo resolves automatically. To
  point elsewhere, set `PRAXIA_WEBSITE_DIR` in `.env`.
- **App screenshots in reels/demos:** captured from the course-factory app if it is running on
  `localhost:5183`; otherwise the reels use the website + stock footage (still fine).
- **Fonts:** the reel/demo captions use Windows system fonts. On Mac/Linux, install Arial or edit the
  font paths in `reel.py` / `demo.py`.
- **Nothing is stored:** reels/demos are built in a temp folder and deleted after posting.
