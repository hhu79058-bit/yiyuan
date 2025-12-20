# Repository Guidelines 
 
## Project Structure & Module Organization 
- `app.py` registers the Flask app and blueprints. 
- `*_routes.py` hold route handlers by area: auth, registration, doctor, patient, pharmacy, payment, stats. 
- `db.py` handles the MySQL connection, schema bootstrapping, and shared queries. 
- `templates/` contains Jinja2 HTML views. 
- `static/` stores CSS and static assets. 
- `utils.py` provides shared auth helpers. 
 
## Build, Test, and Development Commands 
- `pip install flask pymysql` installs runtime dependencies. 
- `python app.py` runs the Flask dev server at `http://127.0.0.1:5000/`. 
- Configure the database in `db.py` (host/user/password/DB name) and ensure the schema exists. 
 
## Coding Style & Naming Conventions 
- Python uses 4-space indentation and `snake_case` for functions and variables. 
- Route modules follow `*_routes.py` naming aligned with their blueprints. 
- Templates in `templates/` should stay paired with their route modules. 
- CSS lives in `static/app.css`; prefer existing utility classes such as `card` and `btn`. 
 
## Testing Guidelines 
- No automated tests are currently present. 
- Validate changes manually: login, scheduling, registration, payment, pharmacy, and stats pages. 
 
## Commit & Pull Request Guidelines 
- No commit message convention is documented; use short, imperative summaries (e.g., Fix schedule validation). 
- PRs should include purpose, affected routes/templates, and screenshots for UI changes. 
- Note any manual test steps performed. 
 
## Configuration & Security Notes 
- `db.py` contains connection credentials and a default admin account; update locally and avoid committing secrets. 
- If you add environment-based config, document it in `README.md`.
