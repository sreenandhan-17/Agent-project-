# 02: Festival holiday dates need verification

> **✅ RESOLVED.** `seed.py` now uses the official 2026 Central Government gazetted list (17 holidays, DoPT OM F.No.12/2/2023-JCA). Corrections: Id-ul-Fitr is **Mar 21** (not Mar 20) and Diwali is **Nov 8** (not Nov 9). Added Ram Navami, Mahavir Jayanti, Buddha Purnima (replacing "Labour Day" on May 1), Bakrid, Muharram, Milad-un-Nabi, Janmashtami and Guru Nanak's Birthday (Nov 24). Re-running the seed now also corrects the names of existing holidays. Source: https://dfe.gov.in/uploads/documents/list-of-gazetted-holidays-2026.pdf. If Arvo follows a different list (for example a state list), edit `HOLIDAYS` in `seed.py`.

**What:** `seed.py` holds the 2026 holidays. The fixed dates are certain: Republic Day (Jan 26), Independence Day (Aug 15), Gandhi Jayanti (Oct 2), Labour Day (May 1) and Christmas (Dec 25). These lunar-calendar dates are best estimates:

| Holiday | Seeded date | Check |
|---|---|---|
| Holi | 2026-03-04 | |
| Id-ul-Fitr | 2026-03-20 | depends on moon sighting |
| Good Friday | 2026-04-03 | |
| Dussehra | 2026-10-20 | |
| Diwali | 2026-11-09 | Lakshmi Puja is Sun Nov 8; is Mon Nov 9 the office holiday? |

**Impact:** A wrong holiday shifts SLA deadlines by a full working day, which can make a ticket wrongly late or wrongly on time.

**Fix:** Confirm the dates against Arvo's official 2026 holiday list. Edit `HOLIDAYS` in `seed.py`, and update or insert the corrected rows in the `holidays` table (re-seeding only adds missing dates; it doesn't change existing ones).
