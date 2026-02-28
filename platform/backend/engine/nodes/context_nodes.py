"""Cross-signal context inference nodes.

These nodes sit *between* raw data sources and bar-specific intent nodes.
They combine multiple upstream signals to produce derived contextual insights
that explain *why* bar traffic is expected at specific times and places.

Pipeline topology:
  Raw Sources → Context Nodes → Bar Intent Nodes → Features → Predictor

Example causal chain modelled here:
  is_greek_formal_season (Oct-Nov / Mar-Apr)
    + Thu/Fri/Sat
    → date_party_tonight (GreekSocialContextNode)
    → sallys_pregame_boost at 3-6 PM (date party starts 9-10 PM; cheap drinks first)
    → kk_after_party_draw at 10 PM+ (KK is primary Greek destination, 0.90× proximity)
"""

from __future__ import annotations

import logging
from datetime import datetime, timezone

log = logging.getLogger(__name__)


# ── GreekSocialContextNode ────────────────────────────────────────────────────

class GreekSocialContextNode:
    """Cross-signal: Greek Life × Academic Calendar → social event context.

    Infers whether a date party / formal is happening tonight, then models
    the full causal chain:

      formal_season + Thu/Fri/Sat
        → date_party_tonight
        → sallys_pregame_boost (3-6 PM, cheap HH drinks before event starts)
        → kk_after_party_draw  (10 PM+, KK is the primary Greek destination)

    Bar proximity weights (GREEK_BAR_PROXIMITY):
        Blarney's 0.75 · Sally's 0.45 · KK 0.90
    """

    node_type = "greek_social_ctx"

    def execute(self, config: dict, inputs: dict) -> dict:
        from providers.greek_life import GREEK_BAR_PROXIMITY

        dt = config.get("datetime") or datetime.now(timezone.utc)
        if isinstance(dt, str):
            dt = datetime.fromisoformat(dt)

        # Merge all upstream signal dicts
        signals: dict = {}
        for out in inputs.values():
            if isinstance(out, dict):
                signals.update(out)

        hour = dt.hour
        dow = dt.weekday()  # 0=Mon … 6=Sun

        is_formal_season    = bool(signals.get("is_greek_formal_season", 0))
        is_bid_day          = bool(signals.get("is_greek_bid_day", 0))
        is_greek_thu        = bool(signals.get("is_greek_thursday", 0))
        is_rush             = bool(signals.get("is_greek_rush_week", 0))
        greek_intensity     = float(signals.get("greek_social_intensity", 0.0))
        is_pregame_window   = bool(signals.get("is_greek_pregame_window", 0))
        classes_in_session  = bool(signals.get("classes_in_session", 0))

        # ── Infer date party tonight ───────────────────────────────────────────
        # Formal season + Thu/Fri/Sat + semester active = high date-party probability
        is_social_weekend_night = dow in (3, 4, 5) and classes_in_session
        date_party_tonight = bool(
            (is_formal_season and is_social_weekend_night and not is_rush)
            or is_bid_day
        )

        # ── Sally's pre-game boost (3-6 PM) ───────────────────────────────────
        # Greeks go to Sally's cheap HH before the date party starts at 9-10 PM.
        # Proximity to Greek row is 0.45 (Stadium Village) — moderate but real.
        sallys_pregame_boost = 0.0
        if date_party_tonight and 15 <= hour < 18:
            # This is THE window: happy hour + pre-party = real surge
            sallys_pregame_boost = 0.52 * GREEK_BAR_PROXIMITY[2]
        elif date_party_tonight and 12 <= hour < 22:
            # Anticipation signal outside the exact HH window
            sallys_pregame_boost = 0.18 * GREEK_BAR_PROXIMITY[2]

        # ── KK after-party draw (10 PM - 2 AM) ────────────────────────────────
        # KK is the primary Greek destination (0.90× proximity), pulls in the
        # after-party crowd once date parties wind down around 10-11 PM.
        kk_after_party_draw = 0.0
        if date_party_tonight and (hour >= 22 or hour <= 2):
            kk_after_party_draw = 0.80 * GREEK_BAR_PROXIMITY[3]
        elif date_party_tonight and 19 <= hour < 22:
            # Pre-party pregame at KK also
            kk_after_party_draw = 0.45 * GREEK_BAR_PROXIMITY[3]

        # ── Blarney's Greek draw (proximity 0.75) ─────────────────────────────
        blarneys_greek_draw = greek_intensity * GREEK_BAR_PROXIMITY[1]
        if is_greek_thu:
            blarneys_greek_draw = min(blarneys_greek_draw * 1.4, 1.0)

        # ── Primary driver narrative ───────────────────────────────────────────
        if is_bid_day:
            driver = "bid_day_surge"
        elif date_party_tonight and 15 <= hour < 18:
            driver = "date_party_pregame_at_sallys"
        elif date_party_tonight and (hour >= 22 or hour <= 2):
            driver = "date_party_afterparty_at_kk"
        elif is_greek_thu:
            driver = "greek_thursday_mixer"
        elif is_formal_season:
            driver = "formal_season_baseline"
        else:
            driver = "standard_social"

        return {
            "date_party_tonight":      int(date_party_tonight),
            "sallys_pregame_boost":    round(sallys_pregame_boost, 3),
            "kk_after_party_draw":     round(kk_after_party_draw, 3),
            "blarneys_greek_draw":     round(blarneys_greek_draw, 3),
            "greek_intensity":         greek_intensity,
            "is_pregame_window":       int(is_pregame_window),
            "is_bid_day":              int(is_bid_day),
            "is_greek_thursday":       int(is_greek_thu),
            "greek_social_driver":     driver,
        }


# ── GameDayContextNode ────────────────────────────────────────────────────────

class GameDayContextNode:
    """Cross-signal: Sports × Weather × Calendar → game day crowd dynamics.

    Models three distinct crowd patterns:
    - Pre-game bar draw (1-3 hrs before kickoff → bars fill as fans pregame)
    - Post-game migration (crowd flows into Dinkytown after game ends)
    - TV sports anchor (big TV games keep people at the bar instead of going home)
    """

    node_type = "game_day_ctx"

    def execute(self, config: dict, inputs: dict) -> dict:
        dt = config.get("datetime") or datetime.now(timezone.utc)
        if isinstance(dt, str):
            dt = datetime.fromisoformat(dt)

        signals: dict = {}
        for out in inputs.values():
            if isinstance(out, dict):
                signals.update(out)

        hour = dt.hour

        is_football_home    = bool(signals.get("is_football_home", 0))
        is_basketball_home  = bool(signals.get("is_basketball_home", 0))
        is_hockey_home      = bool(signals.get("is_hockey_home", 0))
        hours_until_game    = float(signals.get("hours_until_game", 99))
        is_rivalry_game     = bool(signals.get("is_rivalry_game", 0))
        is_nfl_game_day     = bool(signals.get("is_nfl_game_day", 0))
        is_cfb_saturday     = bool(signals.get("is_cfb_saturday", 0))
        is_super_bowl       = bool(signals.get("is_super_bowl", 0))
        tv_game_weight      = float(signals.get("tv_game_weight", 0.0))
        temp_c              = float(signals.get("temperature_c", 10))
        is_severe           = bool(signals.get("is_severe_weather", 0))

        is_home_game = is_football_home or is_basketball_home or is_hockey_home
        rivalry_mult = 1.5 if is_rivalry_game else 1.0

        # ── Pre-game bar draw ──────────────────────────────────────────────────
        # Fans start drinking 1-3 hours before kickoff
        pregame_bar_draw = 0.0
        if is_home_game and 0 < hours_until_game <= 3:
            pregame_bar_draw = 0.60 * (1.0 - hours_until_game / 3.0) * rivalry_mult
            pregame_bar_draw = min(pregame_bar_draw, 1.0)

        # ── Post-game migration ────────────────────────────────────────────────
        # After the game ends, crowds stream out toward Dinkytown
        post_game_migration = 0.0
        if is_home_game and hours_until_game < 0:
            hours_since = -hours_until_game
            if hours_since <= 2.5:
                post_game_migration = 0.70 * (1 - hours_since / 2.5) * rivalry_mult
                post_game_migration = min(post_game_migration, 1.0)

        # ── Weather indoor push ────────────────────────────────────────────────
        # Severe weather or extreme cold pushes people into bars instead of outside
        weather_indoor_push = 0.0
        if is_severe or temp_c < -10:
            weather_indoor_push = 0.18
        elif temp_c < 0:
            weather_indoor_push = 0.08

        # ── TV sports anchor ───────────────────────────────────────────────────
        # Big TV events keep people at the bar watching rather than going home
        tv_anchor_strength = 0.0
        if is_super_bowl:
            tv_anchor_strength = 0.92
        elif is_cfb_saturday and 14 <= hour <= 22:
            tv_anchor_strength = 0.55
        elif is_nfl_game_day and 12 <= hour <= 21:
            tv_anchor_strength = 0.45
        elif tv_game_weight > 0.5:
            tv_anchor_strength = tv_game_weight * 0.6

        # ── Bar-specific boosts ────────────────────────────────────────────────
        # Blarney's is deep in Dinkytown → gets post-game migration crowd
        blarneys_postgame_boost = post_game_migration * 0.75
        # Sally's is in Stadium Village → gets pre-game football foot traffic
        sallys_pregame_boost = pregame_bar_draw * 0.65 if is_football_home else 0.0

        if is_rivalry_game and is_home_game:
            mood = "electric"
        elif is_home_game or is_super_bowl:
            mood = "elevated"
        elif is_cfb_saturday:
            mood = "tv_sports_day"
        else:
            mood = "standard"

        return {
            "is_home_game":             int(is_home_game),
            "pregame_bar_draw":         round(pregame_bar_draw, 3),
            "post_game_migration":      round(post_game_migration, 3),
            "blarneys_postgame_boost":  round(blarneys_postgame_boost, 3),
            "sallys_pregame_boost":     round(sallys_pregame_boost, 3),
            "tv_anchor_strength":       round(tv_anchor_strength, 3),
            "weather_indoor_push":      round(weather_indoor_push, 3),
            "game_day_mood":            mood,
            "is_rivalry_game":          int(is_rivalry_game),
        }


# ── SpecialsClockNode ─────────────────────────────────────────────────────────

class SpecialsClockNode:
    """Context: Current time × Day of week → which bar specials are live right now.

    Reads BAR_SCHEDULES from config and returns real-time deal status per bar.
    Drives bar intent nodes by signaling when cheap drinks are available —
    which directly correlates with which bar is crowded at any given hour.
    """

    node_type = "specials_clock"

    def execute(self, config: dict, inputs: dict) -> dict:
        from config.settings import BAR_SCHEDULES

        dt = config.get("datetime") or datetime.now(timezone.utc)
        if isinstance(dt, str):
            dt = datetime.fromisoformat(dt)

        hour   = dt.hour
        minute = dt.minute
        dow    = dt.weekday()  # 0=Mon, 6=Sun

        def _in_window(sh: int, sm: int, eh: int, em: int) -> bool:
            now_mins = hour * 60 + minute
            s_mins   = sh * 60 + sm
            e_mins   = eh * 60 + em
            if e_mins > 24 * 60:
                # Overnight slot (e.g. end=26:00 → active until 2 AM next day)
                next_day_end = e_mins - 24 * 60
                return now_mins >= s_mins or now_mins <= next_day_end
            return s_mins <= now_mins < e_mins

        result: dict = {}
        active_deals: list[dict] = []

        for bar_id, sched in BAR_SCHEDULES.items():
            hh = sched.get("happy_hour")
            hh_active = False
            if hh and dow in hh.get("days", []):
                sh, sm = hh["start"]
                eh, em = hh["end"]
                hh_active = _in_window(sh, sm, eh, em)

            bar_specials_active: list[str] = []
            for sp in sched.get("weekly_specials", []):
                if dow in sp.get("days", []):
                    sh, sm = sp["start"]
                    eh, em = sp["end"]
                    if _in_window(sh, sm, eh, em):
                        bar_specials_active.append(sp["name"])
                        active_deals.append({
                            "bar_id": bar_id,
                            "deal":   sp["name"],
                            "boost":  sp["traffic_boost"],
                        })

            result[f"bar_{bar_id}_happy_hour"]      = int(hh_active)
            result[f"bar_{bar_id}_specials_active"] = len(bar_specials_active)
            result[f"bar_{bar_id}_deal_names"]      = bar_specials_active

            if hh_active:
                active_deals.append({"bar_id": bar_id, "deal": "Happy Hour", "boost": 0.15})

        # Named flags consumed by bar intent nodes
        result["sallys_happy_hour_active"]  = result.get("bar_2_happy_hour", 0)
        result["sallys_late_hh_active"]     = int(
            dow in range(7) and _in_window(22, 0, 24, 0)
        )
        result["sallys_2_dollar_tuesday"]   = int(
            dow == 1 and _in_window(20, 0, 24, 0)
        )
        result["blarneys_happy_hour_active"]  = result.get("bar_1_happy_hour", 0)
        result["blarneys_karaoke_thursday"]   = int(
            dow == 3 and _in_window(21, 0, 26, 0)
        )
        result["kk_tuesday_special"]   = int(dow == 1 and _in_window(21, 0, 26, 0))
        result["kk_thursday_special"]  = int(dow == 3 and _in_window(21, 0, 26, 0))
        result["kk_friday_after_class"] = int(dow == 4 and _in_window(15, 0, 19, 0))

        result["active_deals_count"] = len(active_deals)
        result["active_deals"]       = active_deals

        return result


# ── AcademicPressureNode ──────────────────────────────────────────────────────

class AcademicPressureNode:
    """Context: Academic Calendar → student social pressure mode.

    Transforms raw academic flags into actionable bar traffic signals:
    - Finals suppression (0.15 social mode — almost nobody going out)
    - Welcome week surge (0.90 — everyone meeting people)
    - Mid-semester sweet spot (weeks 3-8 peak social at 0.80)
    - Pre-break surge: +35% the 2 days before semester break starts
    """

    node_type = "academic_pressure"

    def execute(self, config: dict, inputs: dict) -> dict:
        signals: dict = {}
        for out in inputs.values():
            if isinstance(out, dict):
                signals.update(out)

        is_finals        = bool(signals.get("is_finals_week", 0))
        is_welcome       = bool(signals.get("is_welcome_week", 0))
        is_break         = bool(signals.get("is_break", 0))
        is_midterms      = bool(signals.get("is_midterms_week", 0))
        is_study_days    = bool(signals.get("is_study_days", 0))
        days_until_break = int(signals.get("days_until_break", 999))
        week_of_sem      = int(signals.get("week_of_semester", 0))
        classes_active   = bool(signals.get("classes_in_session", 0))
        is_syllabus_week = bool(signals.get("is_syllabus_week", 0))
        is_summer        = bool(signals.get("is_summer_session", 0))

        # Social mode: 0 = everyone studying, 1 = maximum bar traffic
        if is_finals or is_study_days:
            social_mode = 0.15
            phase = "finals_crunch"
        elif is_break:
            social_mode = 0.25
            phase = "break"
        elif is_welcome:
            social_mode = 0.90
            phase = "welcome_week"
        elif is_syllabus_week:
            social_mode = 0.75
            phase = "syllabus_week"
        elif is_midterms:
            social_mode = 0.45
            phase = "midterms"
        elif 3 <= week_of_sem <= 8:
            social_mode = 0.80
            phase = "peak_social"
        elif 9 <= week_of_sem <= 11:
            social_mode = 0.65
            phase = "settling"
        elif 11 <= week_of_sem <= 14:
            social_mode = 0.70
            phase = "late_semester"
        elif is_summer:
            social_mode = 0.55
            phase = "summer"
        elif not classes_active:
            social_mode = 0.30
            phase = "off_semester"
        else:
            social_mode = 0.60
            phase = "normal"

        # Last-night-before-break surge ("one more night out" effect)
        pre_break_surge = 0.0
        if 0 < days_until_break <= 2 and not is_break:
            pre_break_surge = 0.35 * (1 - days_until_break / 3.0)

        finals_suppression = 0.30 if is_finals else (0.55 if is_study_days else 1.0)
        thirsty_thu_factor = social_mode * 0.85

        return {
            "social_mode_score":       round(social_mode, 3),
            "semester_phase":          phase,
            "pre_break_surge":         round(pre_break_surge, 3),
            "thirsty_thursday_factor": round(thirsty_thu_factor, 3),
            "finals_suppression":      round(finals_suppression, 3),
            "days_until_break":        days_until_break,
            "week_of_semester":        week_of_sem,
        }


# ── SallysIntentNode ──────────────────────────────────────────────────────────

class SallysIntentNode:
    """Bar-specific intent: Sally's Saloon demand aggregation.

    The primary story here is Greek date party pre-game:
      date_party_tonight + sallys_happy_hour_active (3-6 PM)
        → greek_pregame_contribution (the biggest Sally's signal on formal nights)

    Other signals:
    - Specials clock: $2 Tuesday student draw (8 PM - midnight)
    - Game day: football foot traffic through Stadium Village
    - Weather: nice day → patio boost
    - Academic pressure: finals suppression / welcome week surge
    """

    node_type = "sallys_intent"

    def execute(self, config: dict, inputs: dict) -> dict:
        dt = config.get("datetime") or datetime.now(timezone.utc)
        if isinstance(dt, str):
            dt = datetime.fromisoformat(dt)

        signals: dict = {}
        for out in inputs.values():
            if isinstance(out, dict):
                signals.update(out)

        hour = dt.hour

        sallys_greek_boost  = float(signals.get("sallys_pregame_boost", 0.0))
        game_pregame_boost  = float(signals.get("sallys_pregame_boost", 0.0))
        hh_active           = bool(signals.get("sallys_happy_hour_active", 0))
        late_hh_active      = bool(signals.get("sallys_late_hh_active", 0))
        two_dollar_tue      = bool(signals.get("sallys_2_dollar_tuesday", 0))
        social_mode         = float(signals.get("social_mode_score", 0.6))
        finals_suppression  = float(signals.get("finals_suppression", 1.0))
        date_party_tonight  = bool(signals.get("date_party_tonight", 0))
        temp_c              = float(signals.get("temperature_c", 10))
        pre_break_surge     = float(signals.get("pre_break_surge", 0.0))
        tv_anchor           = float(signals.get("tv_anchor_strength", 0.0))

        base_demand     = social_mode * 0.50
        deal_boost      = 0.0
        active_drivers: list[str] = []

        if hh_active:
            deal_boost += 0.25
            active_drivers.append("happy_hour_3_6pm")
        if late_hh_active:
            deal_boost += 0.20
            active_drivers.append("late_happy_hour_10pm")
        if two_dollar_tue:
            deal_boost += 0.30 * social_mode
            active_drivers.append("2_dollar_tuesday")

        # ── Greek date party pre-game (the main Sally's story) ─────────────────
        greek_pregame = 0.0
        if date_party_tonight and hh_active:
            # Peak signal: Greeks pre-gaming during happy hour before date party
            greek_pregame = sallys_greek_boost * 1.4
            active_drivers.append("date_party_pregame_hh")
        elif date_party_tonight:
            greek_pregame = sallys_greek_boost
            active_drivers.append("date_party_pregame")

        # Stadium Village football foot traffic
        game_contrib = game_pregame_boost * 0.40
        if game_pregame_boost > 0.1:
            active_drivers.append("football_foot_traffic")

        # Patio weather: nice day, mid-afternoon to evening
        weather_boost = 0.0
        if 15 <= temp_c <= 28 and 14 <= hour <= 20:
            weather_boost = 0.15
            active_drivers.append("nice_weather_patio")

        if tv_anchor > 0.3:
            deal_boost += tv_anchor * 0.30
            active_drivers.append("tv_sports_draw")

        total = (
            base_demand + deal_boost + greek_pregame + game_contrib
            + weather_boost + pre_break_surge
        ) * finals_suppression
        total = min(total, 1.0)

        if greek_pregame > 0.1 and hh_active:
            primary = "date_party_pregame_at_happy_hour"
        elif two_dollar_tue:
            primary = "2_dollar_tuesday_student_night"
        elif game_pregame_boost > 0.2:
            primary = "football_foot_traffic"
        elif hh_active:
            primary = "standard_happy_hour"
        elif late_hh_active:
            primary = "late_night_deals"
        else:
            primary = "baseline_student_traffic"

        return {
            "sallys_demand_multiplier":  round(total, 3),
            "sallys_primary_driver":     primary,
            "sallys_active_drivers":     active_drivers,
            "sallys_greek_contribution": round(greek_pregame, 3),
            "sallys_deal_boost":         round(deal_boost, 3),
            "sallys_game_contribution":  round(game_contrib, 3),
            "sallys_expected_peak":      22 if late_hh_active else (17 if hh_active else 21),
        }


# ── BlarneysIntentNode ────────────────────────────────────────────────────────

class BlarneysIntentNode:
    """Bar-specific intent: Blarney's Pub demand aggregation.

    Primary signals:
    - Game day context: post-game migration into Dinkytown (main Blarney's driver)
    - Greek social: proximity 0.75 to Greek row → consistent Greek spillover
    - Specials clock: Karaoke Thursday 9 PM-2 AM (+55% boost, institution)
    - Late night draw: drunk migration after 11 PM from other bars
    """

    node_type = "blarneys_intent"

    def execute(self, config: dict, inputs: dict) -> dict:
        dt = config.get("datetime") or datetime.now(timezone.utc)
        if isinstance(dt, str):
            dt = datetime.fromisoformat(dt)

        signals: dict = {}
        for out in inputs.values():
            if isinstance(out, dict):
                signals.update(out)

        hour = dt.hour

        postgame_boost      = float(signals.get("blarneys_postgame_boost", 0.0))
        greek_draw          = float(signals.get("blarneys_greek_draw", 0.0))
        karaoke_thu         = bool(signals.get("blarneys_karaoke_thursday", 0))
        hh_active           = bool(signals.get("blarneys_happy_hour_active", 0))
        social_mode         = float(signals.get("social_mode_score", 0.6))
        finals_suppression  = float(signals.get("finals_suppression", 1.0))
        tv_anchor           = float(signals.get("tv_anchor_strength", 0.0))
        weather_indoor      = float(signals.get("weather_indoor_push", 0.0))
        pre_break_surge     = float(signals.get("pre_break_surge", 0.0))
        is_rivalry          = bool(signals.get("is_rivalry_game", 0))
        is_greek_thu        = bool(signals.get("is_greek_thursday", 0))

        base_demand     = social_mode * 0.45
        active_drivers: list[str] = []

        # Karaoke Thursday: biggest Blarney's night (+55%)
        karaoke_boost = 0.0
        if karaoke_thu:
            karaoke_boost = 0.55
            active_drivers.append("karaoke_thursday")
            if is_greek_thu:
                karaoke_boost += 0.10  # Greek Thu × Karaoke Thu = packed
                active_drivers.append("greek_x_karaoke_overlap")

        # Post-game migration into Dinkytown
        if postgame_boost > 0.1:
            active_drivers.append("post_game_migration")
            if is_rivalry:
                active_drivers.append("rivalry_game_buzz")

        if greek_draw > 0.2:
            active_drivers.append("greek_row_proximity")

        hh_boost = 0.20 if hh_active else 0.0
        if hh_active:
            active_drivers.append("happy_hour_317pm")

        # Late night drunk migration (BAR_SCHEDULES late_night_draw=True)
        late_night_draw = 0.0
        if hour >= 23 or hour <= 2:
            late_night_draw = 0.25
            active_drivers.append("late_night_drunk_migration")

        if tv_anchor > 0.5:
            active_drivers.append("tv_sports_bar")

        total = (
            base_demand + karaoke_boost + postgame_boost
            + greek_draw * 0.50 + hh_boost + late_night_draw
            + weather_indoor + pre_break_surge + tv_anchor * 0.20
        ) * finals_suppression
        total = min(total, 1.0)

        if karaoke_thu:
            primary = "karaoke_thursday_institution"
        elif postgame_boost > 0.3:
            primary = "post_game_surge"
        elif greek_draw > 0.4:
            primary = "greek_thursday_crowd"
        elif late_night_draw > 0:
            primary = "late_night_migration"
        else:
            primary = "dinkytown_baseline"

        return {
            "blarneys_demand_multiplier": round(total, 3),
            "blarneys_primary_driver":    primary,
            "blarneys_active_drivers":    active_drivers,
            "blarneys_karaoke_boost":     round(karaoke_boost, 3),
            "blarneys_postgame_boost":    round(postgame_boost, 3),
            "blarneys_greek_draw":        round(greek_draw * 0.50, 3),
        }


# ── KKIntentNode ──────────────────────────────────────────────────────────────

class KKIntentNode:
    """Bar-specific intent: Kollege Klub demand aggregation.

    KK is the primary Greek destination at UMN (0.90× proximity weight).
    The after-party draw from date parties is the biggest KK signal on
    formal nights — crowds arrive 10 PM+ after date parties wind down.

    Institutional specials:
    - KK Tuesday: +70% boost — a campus institution (9 PM - 2 AM)
    - KK Thursday: +40% boost, amplified when Greek Thursday overlaps
    - Friday After Class: +35% (3-7 PM, post-class happy hour)
    """

    node_type = "kk_intent"

    def execute(self, config: dict, inputs: dict) -> dict:
        dt = config.get("datetime") or datetime.now(timezone.utc)
        if isinstance(dt, str):
            dt = datetime.fromisoformat(dt)

        signals: dict = {}
        for out in inputs.values():
            if isinstance(out, dict):
                signals.update(out)

        hour = dt.hour

        after_party_draw    = float(signals.get("kk_after_party_draw", 0.0))
        greek_intensity     = float(signals.get("greek_intensity", 0.0))
        is_bid_day          = bool(signals.get("is_bid_day", 0))
        is_greek_thu        = bool(signals.get("is_greek_thursday", 0))
        kk_tue              = bool(signals.get("kk_tuesday_special", 0))
        kk_thu              = bool(signals.get("kk_thursday_special", 0))
        kk_fri              = bool(signals.get("kk_friday_after_class", 0))
        social_mode         = float(signals.get("social_mode_score", 0.6))
        finals_suppression  = float(signals.get("finals_suppression", 1.0))
        pre_break_surge     = float(signals.get("pre_break_surge", 0.0))
        date_party_tonight  = bool(signals.get("date_party_tonight", 0))
        thirsty_thu_factor  = float(signals.get("thirsty_thursday_factor", 0.5))

        base_demand     = social_mode * 0.45
        active_drivers: list[str] = []

        # KK Tuesday — a campus institution
        tue_boost = 0.0
        if kk_tue:
            tue_boost = 0.70
            active_drivers.append("kk_tuesday_institution")

        # KK Thursday — amplified by Greek Thursday
        thu_boost = 0.0
        if kk_thu:
            thu_boost = 0.40
            active_drivers.append("kk_thursday_special")
            if is_greek_thu:
                thu_boost *= 1.25  # Greek × KK Thursday = massive night
                active_drivers.append("greek_x_kk_thursday")

        fri_boost = 0.35 if kk_fri else 0.0
        if kk_fri:
            active_drivers.append("friday_after_class")

        if after_party_draw > 0.1:
            active_drivers.append("date_party_after_party")

        bid_day_boost = 0.0
        if is_bid_day:
            bid_day_boost = 0.85
            active_drivers.append("bid_day_peak_night")

        # KK is Greek central — 0.90× proximity drives consistent baseline
        greek_baseline = greek_intensity * 0.55

        # Late night is prime time for KK
        late_night_mult = 1.0
        if hour >= 22 or hour <= 2:
            late_night_mult = 1.30
            if date_party_tonight:
                late_night_mult = 1.55  # After-party amplification

        total = (
            base_demand + tue_boost + thu_boost + fri_boost
            + after_party_draw + bid_day_boost + greek_baseline + pre_break_surge
        ) * late_night_mult * finals_suppression
        total = min(total, 1.0)

        if is_bid_day:
            primary = "bid_day_greek_congregation"
        elif kk_tue:
            primary = "kk_tuesday_institution"
        elif kk_thu and is_greek_thu:
            primary = "greek_x_kk_thursday_peak"
        elif after_party_draw > 0.4:
            primary = "date_party_after_party"
        elif kk_fri:
            primary = "friday_after_class_draw"
        else:
            primary = "greek_central_baseline"

        return {
            "kk_demand_multiplier":  round(total, 3),
            "kk_primary_driver":     primary,
            "kk_active_drivers":     active_drivers,
            "kk_after_party_draw":   round(after_party_draw, 3),
            "kk_greek_baseline":     round(greek_baseline, 3),
            "kk_tue_boost":          round(tue_boost, 3),
            "kk_thu_boost":          round(thu_boost, 3),
            "kk_bid_day_boost":      round(bid_day_boost, 3),
            "kk_expected_peak_hour": 23 if (kk_tue or kk_thu or date_party_tonight) else 22,
        }


# ── Registry ──────────────────────────────────────────────────────────────────

CONTEXT_NODE_REGISTRY: dict[str, type] = {
    "greek_social_ctx":   GreekSocialContextNode,
    "game_day_ctx":       GameDayContextNode,
    "specials_clock":     SpecialsClockNode,
    "academic_pressure":  AcademicPressureNode,
    "sallys_intent":      SallysIntentNode,
    "blarneys_intent":    BlarneysIntentNode,
    "kk_intent":          KKIntentNode,
}
