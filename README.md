# Movies-and-TVSeries-Stuff

A couple of scripts for analyzing movies and TV series data.

## TV Series Ratings Plotter

Visualize IMDb episode ratings across all seasons of a TV series with scatter plots and trend lines.

### Installation

```bash
uv sync
```

Or with pip:
```bash
pip install -e .
```

### Usage

**CLI:**
```bash
python tv_series_ratings.py "Breaking Bad"
```

**Jupyter Notebook:**
Open [tv_series_ratings.ipynb](tv_series_ratings.ipynb) and run the cells to generate plots interactively.

### How it works

The tool scrapes IMDb's episode pages to extract ratings for each episode across all seasons, then plots them with:
- Scatter points for each episode's rating
- Linear trend lines per season
- Dark theme styling

### Examples

Try these series:
- `python tv_series_ratings.py "Game of Thrones"`
- `python tv_series_ratings.py "The Americans"`
- `python tv_series_ratings.py "Orphan Black"`

## Web App

A live web interface is available for visualizing ratings without installing anything locally.

### Deployment

The project includes a serverless backend (Vercel) + static frontend (GitHub Pages) setup:

**1. Deploy the API to Vercel:**

```bash
# Install Vercel CLI
npm i -g vercel

# Deploy from project root
vercel
```

Follow the prompts. Vercel will deploy the Python serverless function from `/api/ratings.py`.

**2. Update the frontend with your API URL:**

Edit `docs/index.html` and replace `YOUR_VERCEL_URL_HERE` with your Vercel deployment URL:
```javascript
const API_URL = 'https://your-project.vercel.app/api/ratings';
```

**3. Enable GitHub Pages:**

- Go to your repository Settings → Pages
- Set Source to "Deploy from a branch"
- Select branch `main` and folder `/docs`
- Save

Your web app will be live at `https://yourusername.github.io/your-repo-name/`

### Architecture

- **Frontend** (`/docs/index.html`): Static HTML/CSS/JS hosted on GitHub Pages, uses Chart.js for visualization
- **Backend** (`/api/ratings.py`): Python serverless function on Vercel that scrapes IMDb and returns JSON
- **CORS**: Enabled on the API to allow cross-origin requests from GitHub Pages

### Notes

- The original `IMDB-TVSeries.ipynb` notebook relied on the `cinemagoer` library, which no longer works for fetching episode data due to IMDb's website redesign.
- The new implementation uses direct HTML scraping with `requests` + `BeautifulSoup` to reliably fetch current data.
- The web app may take a few seconds to load results as it scrapes IMDb in real-time.

