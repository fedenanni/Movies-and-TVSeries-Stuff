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

