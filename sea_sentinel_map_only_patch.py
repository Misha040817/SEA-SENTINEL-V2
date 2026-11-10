from pathlib import Path
from datetime import datetime
import shutil, ast, json, re

p = Path('ais_tracking/ais_dashboard_neon.py')
geo = Path('ais_tracking/malaysia_states.geojson')
if not p.is_file() or not geo.is_file():
    raise SystemExit('Missing ais_dashboard_neon.py or malaysia_states.geojson; no changes made.')
features = json.loads(geo.read_text(encoding='utf-8-sig'))
if features.get('type') != 'FeatureCollection' or not features.get('features'):
    raise SystemExit('Invalid state GeoJSON; no changes made.')
original = p.read_text(encoding='utf-8-sig')
match = re.search(r'(?m)^def make_map\(df, region\):', original)
end = re.search(r'(?m)^def chart_style\(', original)
if not match or not end or end.start() <= match.start():
    raise SystemExit('Unexpected map function layout; no changes made.')
new_map = '''def make_map(df, region):
    # Map-only visual update: preserve existing AIS loading, charts and layout.
    lat, lon, zoom = REGIONS[region]
    if region == 'Malaysia':
        lat, lon, zoom = 4.0, 109.0, 4.1

    # Colours are movement categories, NOT threat assessment results.
    colors = {
        'Moving': [184, 255, 0, 245],
        'Slow': [255, 224, 0, 245],
        'Stationary / Unknown': [255, 139, 0, 245],
    }
    dots = df.copy()
    if not dots.empty:
        dots['color'] = dots['movement'].map(colors)
        dots['color'] = dots['color'].apply(
            lambda c: c if isinstance(c, list) else [255, 54, 54, 245]
        )

    with open(BASE / 'malaysia_states.geojson', encoding='utf-8-sig') as f:
        states = json.load(f)

    # A filled polygon, followed by a narrow crisp border; no thick spikes.
    boundary_layers = [
        pdk.Layer('GeoJsonLayer', states,
                  filled=True, stroked=True,
                  get_fill_color=[9, 53, 31, 125],
                  get_line_color=[53, 215, 90, 180],
                  get_line_width=1.1, line_width_units='pixels',
                  pickable=False),
    ]

    state_labels = [
        ('Perlis', 6.55, 100.18), ('Kedah', 6.03, 100.72),
        ('Pulau Pinang', 5.40, 100.26), ('Perak', 4.76, 101.02),
        ('Kelantan', 5.84, 102.13), ('Terengganu', 5.06, 103.02),
        ('Pahang', 3.83, 102.55), ('Selangor', 3.20, 101.42),
        ('N. Sembilan', 2.75, 102.15), ('Melaka', 2.24, 102.24),
        ('Johor', 2.12, 103.45), ('Sabah', 5.72, 116.28),
        ('Sarawak', 2.86, 113.08),
    ]
    labels = pd.DataFrame([
        {'name': name, 'latitude': la, 'longitude': lo}
        for name, la, lo in state_labels
    ])
    countries = pd.DataFrame([
        {'name': n, 'latitude': la, 'longitude': lo}
        for n, la, lo in [
            ('THAILAND', 14.3, 100.8), ('VIETNAM', 15.7, 108.0),
            ('CAMBODIA', 12.6, 104.9), ('PHILIPPINES', 12.7, 122.7),
            ('INDONESIA', -2.1, 117.2), ('BRUNEI', 4.55, 114.75),
            ('SINGAPORE', 1.29, 103.85),
        ]
    ])
    layers = boundary_layers + [
        pdk.Layer('ScatterplotLayer', dots,
                  get_position='[longitude, latitude]',
                  get_fill_color='color', get_radius=500,
                  radius_min_pixels=2.5, radius_max_pixels=4.5,
                  pickable=True, auto_highlight=True),
        pdk.Layer('TextLayer', labels,
                  get_position='[longitude, latitude]',
                  get_text='name', get_size=16, size_units='pixels',
                  get_color=[255, 255, 255, 255],
                  get_text_anchor='middle',
                  get_alignment_baseline='center',
                  font_family='Arial, sans-serif', font_weight=800,
                  pickable=False),
        pdk.Layer('TextLayer', countries,
                  get_position='[longitude, latitude]',
                  get_text='name', get_size=18, size_units='pixels',
                  get_color=[255, 255, 255, 255],
                  get_text_anchor='middle',
                  get_alignment_baseline='center',
                  font_family='Arial, sans-serif', font_weight=800,
                  pickable=False),
    ]
    deck = pdk.Deck(
        layers=layers,
        initial_view_state=pdk.ViewState(
            latitude=lat, longitude=lon, zoom=zoom, pitch=0),
        map_style='https://basemaps.cartocdn.com/gl/dark-matter-gl-style/style.json',
        tooltip={
            'html': '<b>{name}</b><br/>MMSI: {mmsi}<br/>Source: {source}<br/>Speed: {speed_knots} kn<br/>Coordinates: {latitude}, {longitude}<br/>Observed: {last_seen}',
            'style': {'backgroundColor': '#06172A', 'color': 'white',
                      'border': '1px solid #B8FF00'},
        },
    )
    st.pydeck_chart(deck, height=510, use_container_width=True)
    st.caption('Lime: moving (>5 kn) | Yellow: slow (0.5–5 kn) | Orange: stationary/unknown | Red: uncategorised. Dots are actual recent AIS positions, not simulated traffic.')


'''
updated = original[:match.start()] + new_map + original[end.start():]
# Make all Streamlit UI text white and readable without changing layout.
css = '''
/* SEA SENTINEL map-theme legibility patch */
.stApp, .stApp p, .stApp label, .stApp h1, .stApp h2, .stApp h3,
[data-testid="stSidebar"] p, [data-testid="stSidebar"] label,
[data-testid="stMetricLabel"], [data-testid="stCaptionContainer"],
[data-testid="stMarkdownContainer"] {color:#F7FBFF !important; font-weight:650;}
[data-testid="stSidebar"] [role="radiogroup"] label p {color:#FFFFFF !important; font-weight:750 !important;}
[data-testid="stSelectbox"] label, [data-testid="stSelectbox"] span {color:#FFFFFF !important;}
'''
css_anchor = '</style>""", unsafe_allow_html=True)'
if css_anchor not in updated:
    raise SystemExit('Could not safely locate CSS block; no changes made.')
updated = updated.replace(css_anchor, css + css_anchor, 1)
ast.parse(updated)
backup = p.with_name('ais_dashboard_neon_backup_' + datetime.now().strftime('%Y%m%d_%H%M%S') + '.py')
shutil.copy2(p, backup)
p.write_text(updated, encoding='utf-8')
print('SUCCESS: map-only style updated. Existing dashboard layout and AIS logic preserved.')
print('Backup:', backup)
print('GeoJSON features:', len(features['features']))
print('Note: existing CARTO basemap remains; dark navy ocean requires a separate basemap adjustment.')
