/**
 * ontology.js — Shared Ontology panel for all UMN Bar Tracker pages.
 * Self-injects CSS, panel HTML, and nav tab. No dependencies.
 */
(function () {
  /* ── CSS ─────────────────────────────────────────────────────── */
  const style = document.createElement('style');
  style.textContent = `
    .onto-btn {
      padding: 7px 14px;
      background: transparent;
      border: 1px solid rgba(232,160,32,.13);
      color: rgba(237,224,204,.6);
      font-family: 'Inconsolata', monospace;
      font-size: 10px;
      letter-spacing: .14em;
      text-transform: uppercase;
      cursor: pointer;
      transition: all .2s;
    }
    .onto-btn:hover, .onto-btn.open {
      border-color: #e8a020;
      color: #ffb533;
      background: rgba(232,160,32,.06);
    }
    #onto {
      position: fixed;
      bottom: 0; left: 0; right: 0;
      z-index: 9000;
      background: rgba(7,4,10,.97);
      border-top: 1.5px solid rgba(232,160,32,.35);
      backdrop-filter: blur(14px);
      transform: translateY(100%);
      transition: transform .38s cubic-bezier(.4,0,.2,1);
      max-height: 64vh;
      display: flex;
      flex-direction: column;
      font-family: 'Inconsolata', monospace;
    }
    #onto.open { transform: translateY(0); }
    .onto-hdr {
      display: flex;
      align-items: center;
      gap: 1.2rem;
      padding: 0 1.4rem;
      height: 42px;
      border-bottom: 1px solid rgba(232,160,32,.13);
      flex-shrink: 0;
    }
    .onto-title {
      font-family: 'Anton', sans-serif;
      font-size: .95rem;
      letter-spacing: .1em;
      color: #e8a020;
    }
    .onto-sub {
      font-size: .48rem;
      letter-spacing: .2em;
      color: rgba(237,224,204,.3);
      text-transform: uppercase;
    }
    .onto-tabs { display: flex; gap: .1rem; margin-left: auto; }
    .onto-tab {
      font-family: 'Inconsolata', monospace;
      font-size: .5rem;
      letter-spacing: .22em;
      text-transform: uppercase;
      padding: .27rem .75rem;
      background: transparent;
      border: 1px solid transparent;
      color: rgba(237,224,204,.3);
      cursor: pointer;
      transition: color .2s, border-color .2s;
    }
    .onto-tab.active {
      color: #e8a020;
      border-color: rgba(232,160,32,.13);
      background: rgba(232,160,32,.07);
    }
    .onto-tab:hover:not(.active) {
      color: rgba(237,224,204,.6);
      border-color: rgba(232,160,32,.13);
    }
    .onto-close {
      font-size: .85rem;
      background: transparent;
      border: none;
      color: rgba(237,224,204,.3);
      cursor: pointer;
      padding: .2rem .45rem;
      transition: color .2s;
      line-height: 1;
      font-family: 'Inconsolata', monospace;
    }
    .onto-close:hover { color: #ede0cc; }
    .onto-body { overflow-y: auto; flex: 1; padding: 1rem 1.4rem 1.2rem; }
    .onto-body.ob-hidden { display: none; }
    .onto-sig-grid {
      display: grid;
      grid-template-columns: repeat(auto-fill, minmax(265px, 1fr));
      gap: .65rem;
    }
    .sig-card {
      border: 1px solid rgba(232,160,32,.13);
      border-left: 3px solid var(--sc, #e8a020);
      background: #13101a;
      padding: .7rem .8rem;
    }
    .sig-card-hdr { display: flex; align-items: baseline; gap: .45rem; margin-bottom: .3rem; }
    .sig-icon { font-size: .85rem; }
    .sig-cat {
      font-family: 'Anton', sans-serif;
      font-size: .66rem;
      letter-spacing: .08em;
      color: var(--sc, #e8a020);
    }
    .sig-meta { font-size: .46rem; letter-spacing: .14em; color: rgba(237,224,204,.3); margin-left: auto; }
    .sig-insight { font-size: .57rem; color: rgba(237,224,204,.6); line-height: 1.55; margin-bottom: .45rem; }
    .sig-chips { display: flex; flex-wrap: wrap; gap: 2px; }
    .sig-chip {
      font-size: .43rem; letter-spacing: .08em; padding: 1px 4px;
      background: rgba(255,255,255,.03); border: 1px solid rgba(255,255,255,.07);
      color: rgba(237,224,204,.3);
    }
    .onto-ent-grid { display: grid; grid-template-columns: repeat(2,1fr); gap: .7rem; max-width: 960px; }
    .ent-card { border: 1px solid rgba(232,160,32,.13); background: #13101a; padding: .75rem 1rem; }
    .ent-name {
      font-family: 'Anton', sans-serif; font-size: .78rem; letter-spacing: .1em;
      color: #e8a020; margin-bottom: .35rem;
      border-bottom: 1px solid rgba(232,160,32,.13); padding-bottom: .28rem;
    }
    .ent-props { font-size: .54rem; color: rgba(237,224,204,.6); line-height: 1.85; }
    .ent-prop-k { color: rgba(237,224,204,.3); }
    .onto-ctx-feed { display: flex; flex-direction: column; gap: .55rem; max-width: 860px; }
    .ctx-item {
      display: flex; gap: .7rem; align-items: flex-start;
      border: 1px solid rgba(232,160,32,.13); border-left: 3px solid var(--ic, #e8a020);
      background: #13101a; padding: .65rem .8rem;
    }
    .ctx-dot {
      width: 7px; height: 7px; border-radius: 50%;
      background: var(--ic, #e8a020); box-shadow: 0 0 5px var(--ic, #e8a020);
      flex-shrink: 0; margin-top: 3px;
    }
    .ctx-text { font-size: .58rem; line-height: 1.6; color: rgba(237,224,204,.6); }
    .ctx-text strong { font-size: .6rem; color: #ede0cc; font-weight: 600; }
  `;
  document.head.appendChild(style);

  /* ── PANEL HTML ──────────────────────────────────────────────── */
  const panel = document.createElement('div');
  panel.id = 'onto';
  panel.innerHTML = `
    <div class="onto-hdr">
      <span class="onto-title">ONTOLOGY</span>
      <span class="onto-sub">Signal semantic map · what the data means</span>
      <div class="onto-tabs">
        <button class="onto-tab active" onclick="ontoSwitchTab('dict',this)">SIGNAL DICTIONARY</button>
        <button class="onto-tab" onclick="ontoSwitchTab('ent',this)">ENTITIES</button>
        <button class="onto-tab" onclick="ontoSwitchTab('ctx',this)">LIVE CONTEXT</button>
      </div>
      <button class="onto-close" onclick="ontoToggle()">✕</button>
    </div>

    <!-- SIGNAL DICTIONARY -->
    <div id="ob-dict" class="onto-body">
      <div class="onto-sig-grid">

        <div class="sig-card" style="--sc:#c0b0f0">
          <div class="sig-card-hdr"><span class="sig-icon">⏰</span><span class="sig-cat">TIME FEATURES</span><span class="sig-meta">10 FEATURES · COMPUTED</span></div>
          <div class="sig-insight">Hour of day + day of week drive ~40% of predictions. Cyclical sin/cos encoding eliminates the midnight-boundary discontinuity. Late-night (12–2 AM) and Thursday are the two highest-impact time signals.</div>
          <div class="sig-chips"><span class="sig-chip">hour</span><span class="sig-chip">day_of_week</span><span class="sig-chip">hour_sin</span><span class="sig-chip">hour_cos</span><span class="sig-chip">dow_sin / dow_cos</span><span class="sig-chip">is_weekend</span><span class="sig-chip">is_thursday</span><span class="sig-chip">is_late_night</span><span class="sig-chip">month</span></div>
        </div>

        <div class="sig-card" style="--sc:#d868a0">
          <div class="sig-card-hdr"><span class="sig-icon">🏛</span><span class="sig-cat">GREEK LIFE</span><span class="sig-meta">7 SIGNALS · COMPUTED</span></div>
          <div class="sig-insight">~3,000 UMN members across 24 IFC fraternities + 13 PHC sororities. Bid Day = single biggest bar night of the semester — entire chapter + dates pregame at bars (7–10 PM) before the event. Rush Week suppresses traffic — many chapters go dry. KK gets 90% of Greek foot traffic.</div>
          <div class="sig-chips"><span class="sig-chip">is_greek_bid_day</span><span class="sig-chip">is_greek_thursday</span><span class="sig-chip">is_greek_formal_season</span><span class="sig-chip">is_greek_pregame_window</span><span class="sig-chip">greek_social_intensity</span><span class="sig-chip">is_greek_rush_week</span><span class="sig-chip">is_greek_week</span></div>
        </div>

        <div class="sig-card" style="--sc:#00cfff">
          <div class="sig-card-hdr"><span class="sig-icon">⛅</span><span class="sig-cat">WEATHER</span><span class="sig-meta">8 SIGNALS · LIVE (Open-Meteo)</span></div>
          <div class="sig-insight">Sub-zero temps + snow drives people indoors → bar surge. Blarney's late-night draw spikes in cold weather as people migrate inside after 10 PM. First nice spring day causes the opposite — crowds disperse outdoors. Severe weather (WMO codes 75–99) triggers dramatic indoor surge.</div>
          <div class="sig-chips"><span class="sig-chip">temperature_c</span><span class="sig-chip">wind_chill_c</span><span class="sig-chip">precipitation_mm</span><span class="sig-chip">snowfall_mm</span><span class="sig-chip">wind_speed_ms</span><span class="sig-chip">is_severe_weather</span><span class="sig-chip">cloud_cover</span><span class="sig-chip">is_first_nice_day</span></div>
        </div>

        <div class="sig-card" style="--sc:#56a85c">
          <div class="sig-card-hdr"><span class="sig-icon">📚</span><span class="sig-cat">ACADEMICS</span><span class="sig-meta">12 SIGNALS · COMPUTED</span></div>
          <div class="sig-insight">classes_in_session is the single strongest binary predictor in the model. Finals week → bars go nearly silent. Welcome/syllabus week → heavy traffic (no homework yet). week_of_semester (1–16) captures the full semester arc. Summer = dramatically lower baseline for all bars.</div>
          <div class="sig-chips"><span class="sig-chip">classes_in_session</span><span class="sig-chip">is_finals_week</span><span class="sig-chip">is_welcome_week</span><span class="sig-chip">is_midterms_week</span><span class="sig-chip">is_break</span><span class="sig-chip">week_of_semester</span><span class="sig-chip">days_until_break</span><span class="sig-chip">is_study_days</span><span class="sig-chip">is_commencement</span><span class="sig-chip">+ 3 more</span></div>
        </div>

        <div class="sig-card" style="--sc:#ffb533">
          <div class="sig-card-hdr"><span class="sig-icon">🏈</span><span class="sig-cat">UMN ATHLETICS</span><span class="sig-meta">5 SIGNALS · LIVE (ESPN)</span></div>
          <div class="sig-insight">Football home games are the largest UMN athletic draw. Basketball home games drive Sally's TV crowd. hours_until_game gives the pregame ramp: bars fill 2–3 hours before kickoff. Rivalry games add a 1.5× multiplier on top of the base crowd signal.</div>
          <div class="sig-chips"><span class="sig-chip">is_football_home</span><span class="sig-chip">is_basketball_home</span><span class="sig-chip">is_hockey_home</span><span class="sig-chip">hours_until_game</span><span class="sig-chip">is_rivalry_game</span></div>
        </div>

        <div class="sig-card" style="--sc:#ff8844">
          <div class="sig-card-hdr"><span class="sig-icon">📺</span><span class="sig-cat">TV SPORTS</span><span class="sig-meta">13 SIGNALS · LIVE (ESPN)</span></div>
          <div class="sig-insight">Super Bowl and March Madness Elite are the largest TV-driven bar nights of the year — all three bars surge simultaneously. Vikings game day has the strongest weekly MN correlation. tv_game_weight is a continuous 0–1 composite so the model splits on magnitude, not 13 sparse flags.</div>
          <div class="sig-chips"><span class="sig-chip">is_super_bowl</span><span class="sig-chip">is_march_madness_elite</span><span class="sig-chip">is_vikings_game</span><span class="sig-chip">is_nfl_playoffs</span><span class="sig-chip">is_nba_playoffs</span><span class="sig-chip">is_wild_game</span><span class="sig-chip">is_timberwolves_game</span><span class="sig-chip">tv_game_weight</span><span class="sig-chip">+ 5 more</span></div>
        </div>

        <div class="sig-card" style="--sc:#f0a040">
          <div class="sig-card-hdr"><span class="sig-icon">🎃</span><span class="sig-cat">SOCIAL EVENTS</span><span class="sig-meta">8 SIGNALS · COMPUTED</span></div>
          <div class="sig-insight">St. Patrick's Day is the single biggest bar night of the year at UMN — all three bars at capacity. Halloween concentrates at KK. Blackout Wednesday rivals a mid-tier holiday. drinking_holiday_weight is a continuous composite so the RF splits on holiday magnitude rather than 8 sparse flags.</div>
          <div class="sig-chips"><span class="sig-chip">is_st_patricks</span><span class="sig-chip">is_halloween</span><span class="sig-chip">is_blackout_wednesday</span><span class="sig-chip">is_new_years_eve</span><span class="sig-chip">is_homecoming</span><span class="sig-chip">is_cinco_de_mayo</span><span class="sig-chip">drinking_holiday_weight</span><span class="sig-chip">is_bar_crawl</span></div>
        </div>

        <div class="sig-card" style="--sc:#e8a020">
          <div class="sig-card-hdr"><span class="sig-icon">🍺</span><span class="sig-cat">BAR SPECIALS</span><span class="sig-meta">4 SIGNALS · CONFIG</span></div>
          <div class="sig-insight">KK Tuesday +70% is the strongest recurring special in the system — a campus institution. Bar specials are computed deterministically from (bar_id, timestamp), never stored in the DB. minutes_into_special captures the intra-special crowd arc — bars fill up ~40–60 min after a special opens.</div>
          <div class="sig-chips"><span class="sig-chip">is_happy_hour</span><span class="sig-chip">is_bar_special</span><span class="sig-chip">minutes_into_special</span><span class="sig-chip">bar_late_draw</span></div>
        </div>

        <div class="sig-card" style="--sc:#c060e0">
          <div class="sig-card-hdr"><span class="sig-icon">🎟</span><span class="sig-cat">LOCAL EVENTS</span><span class="sig-meta">5 SIGNALS · LIVE (SeatGeek)</span></div>
          <div class="sig-insight">Large events (>500 cap) within 2 km of Dinkytown generate pre/post-event bar surges. Bar crawl flag is a campus organizer signal — when an organized crawl is scheduled, all three bars see simultaneous surge at 9 PM. Cover charge (KK Thu–Sat) directly reduces demand elasticity.</div>
          <div class="sig-chips"><span class="sig-chip">events_nearby</span><span class="sig-chip">has_large_event</span><span class="sig-chip">is_bar_crawl</span><span class="sig-chip">cover_charge</span><span class="sig-chip">nearest_dist_km</span></div>
        </div>

      </div>
    </div>

    <!-- ENTITIES -->
    <div id="ob-ent" class="onto-body ob-hidden">
      <div class="onto-ent-grid">
        <div class="ent-card">
          <div class="ent-name">BAR</div>
          <div class="ent-props">
            <div><span class="ent-prop-k">id · </span>int — 1 (Blarney's) · 2 (Sally's) · 3 (Kollege Klub)</div>
            <div><span class="ent-prop-k">neighborhood · </span>Dinkytown (1, 3) · Stadium Village (2)</div>
            <div><span class="ent-prop-k">capacity · </span>Blarney's ~400 · Sally's ~1,000 · KK ~500</div>
            <div><span class="ent-prop-k">greek_proximity · </span>KK 0.90 · Blarney's 0.75 · Sally's 0.45</div>
            <div><span class="ent-prop-k">specials · </span>happy_hour · weekly_specials · late_night_draw (Blarney's only)</div>
            <div><span class="ent-prop-k">outputs · </span>wait_minutes · pct_full · confidence · model_used</div>
          </div>
        </div>
        <div class="ent-card">
          <div class="ent-name">SIGNAL</div>
          <div class="ent-props">
            <div><span class="ent-prop-k">name · </span>str — e.g. "is_greek_bid_day", "temperature_c"</div>
            <div><span class="ent-prop-k">value · </span>int 0/1 (binary flags) or float (continuous scores)</div>
            <div><span class="ent-prop-k">category · </span>greek_life · weather · academic · sports · events · time</div>
            <div><span class="ent-prop-k">source · </span>live API · static computed from date · config schedule</div>
            <div><span class="ent-prop-k">cache_ttl · </span>0 computed · 600s weather · 3,600s sports/events</div>
            <div><span class="ent-prop-k">feeds_into · </span>FeatureBuilder → WaitTimeModel (RandomForest)</div>
          </div>
        </div>
        <div class="ent-card">
          <div class="ent-name">PREDICTION</div>
          <div class="ent-props">
            <div><span class="ent-prop-k">bar_id · </span>int — which bar this result is for</div>
            <div><span class="ent-prop-k">wait_minutes · </span>float — estimated queue time at the door</div>
            <div><span class="ent-prop-k">pct_full · </span>float 0–1 — estimated crowd density ratio</div>
            <div><span class="ent-prop-k">confidence · </span>HIGH / MED / LOW — density of similar training samples</div>
            <div><span class="ent-prop-k">model_used · </span>"ml (RF)" primary · "baseline (median)" fallback</div>
            <div><span class="ent-prop-k">input_count · </span>75 signal features + 10 time features = 85 total</div>
          </div>
        </div>
        <div class="ent-card">
          <div class="ent-name">EVENT</div>
          <div class="ent-props">
            <div><span class="ent-prop-k">type · </span>greek · academic · drinking holiday · sports · local</div>
            <div><span class="ent-prop-k">magnitude · </span>0–1 continuous (bid_day=0.85 · st_patricks=0.95)</div>
            <div><span class="ent-prop-k">affected_bars · </span>bar_ids with nonzero proximity weight for that event type</div>
            <div><span class="ent-prop-k">pregame_window · </span>7–10 PM before events → bar fills ahead of event start</div>
            <div><span class="ent-prop-k">spillback · </span>11 PM–2 AM after events → late-night surge (Blarney's draw)</div>
            <div><span class="ent-prop-k">examples · </span>Bid Day · KK Tuesday · Super Bowl · St. Patrick's Day</div>
          </div>
        </div>
      </div>
    </div>

    <!-- LIVE CONTEXT -->
    <div id="ob-ctx" class="onto-body ob-hidden">
      <div class="onto-ctx-feed">
        <div class="ctx-item" style="--ic:#56a85c">
          <div class="ctx-dot"></div>
          <div class="ctx-text"><strong>ACADEMIC —</strong> Classes in session, Week 6 of 16. No finals suppression, no welcome-week surge. Typical mid-semester baseline: bars at 55–70% of peak Thursday capacity. Next suppressor: midterms begin week 7.</div>
        </div>
        <div class="ctx-item" style="--ic:#d868a0">
          <div class="ctx-dot"></div>
          <div class="ctx-text"><strong>GREEK LIFE —</strong> Week 6, active semester. No Rush Week suppression (rush ended week 4). Greek Thursday active — IFC chapter mixers running tonight. Pregame window (7–10 PM) will drive KK toward 80%+ capacity. KK greek_proximity 0.90 = highest impact bar. Formal season begins October.</div>
        </div>
        <div class="ctx-item" style="--ic:#00cfff">
          <div class="ctx-dot"></div>
          <div class="ctx-text"><strong>WEATHER —</strong> −2.1°C with 1.2 mm snowfall, wind chill −8.4°C, winds 6.8 m/s. Cold snap driving foot traffic indoors. Blarney's late_night_draw elevated — people migrate inside after 10 PM. Expect +10–15% indoor crowd vs a mild night.</div>
        </div>
        <div class="ctx-item" style="--ic:#ffb533">
          <div class="ctx-dot"></div>
          <div class="ctx-text"><strong>ATHLETICS —</strong> Basketball home game tonight, tipoff in ~5.5 h. Sally's TV crowd will build through the 2nd half (8–10 PM peak). is_rivalry_game: false — standard multiplier. Bars see pre-game foot traffic in the 3–5 h window before tipoff.</div>
        </div>
        <div class="ctx-item" style="--ic:#ff8844">
          <div class="ctx-dot"></div>
          <div class="ctx-text"><strong>TV SPORTS —</strong> tv_game_weight: 0.65 (moderate). Basketball home is the dominant sports signal tonight. No Super Bowl, no March Madness, no Vikings game. Minor MN pro sports signal only (Wild: false, Timberwolves: false).</div>
        </div>
        <div class="ctx-item" style="--ic:#e8a020">
          <div class="ctx-dot"></div>
          <div class="ctx-text"><strong>COMBINED OUTLOOK —</strong> HIGH CONFIDENCE night. Greek Thursday + cold weather + basketball home = elevated, stacked demand. <strong>KK leads at 81% full, ~22 min wait</strong> (KK Thu special +40%; Greek pregame). <strong>Blarney's 68%, ~14 min</strong> (Karaoke Thu +55%; cold migration draw). <strong>Sally's 52%, ~8 min</strong> (basketball TV crowd building). All three bars using RandomForest at HIGH confidence.</div>
        </div>
      </div>
    </div>
  `;
  document.body.appendChild(panel);

  /* ── NAV TAB ─────────────────────────────────────────────────── */
  function injectNavTab() {
    const nav = document.querySelector('.hd-nav');
    if (!nav || document.getElementById('onto-nav-tab')) return;
    const tab = document.createElement('a');
    tab.className = 'nav-tab';
    tab.href = '#';
    tab.id = 'onto-nav-tab';
    tab.textContent = 'Ontology';
    tab.addEventListener('click', function (e) { e.preventDefault(); ontoToggle(); });
    nav.appendChild(tab);
  }

  /* ── LOGIC ───────────────────────────────────────────────────── */
  window.ontoToggle = function () {
    const open = panel.classList.toggle('open');
    const navTab = document.getElementById('onto-nav-tab');
    if (navTab) navTab.classList.toggle('active', open);
    // also sync the sub-header button if present (pipeline page)
    const subBtn = document.getElementById('ontobtn');
    if (subBtn) subBtn.classList.toggle('open', open);
  };

  window.ontoSwitchTab = function (tab, el) {
    panel.querySelectorAll('.onto-tab').forEach(t => t.classList.remove('active'));
    el.classList.add('active');
    ['dict', 'ent', 'ctx'].forEach(function (id) {
      const body = document.getElementById('ob-' + id);
      if (body) body.classList.toggle('ob-hidden', id !== tab);
    });
  };

  // Wait for DOM then inject nav tab
  if (document.readyState === 'loading') {
    document.addEventListener('DOMContentLoaded', injectNavTab);
  } else {
    injectNavTab();
  }
})();
