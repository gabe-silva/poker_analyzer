# Data Extraction Bug Fix Summary

## Problem
The poker analyzer was extracting the same statistics from completely different hand history files, suggesting the data wasn't being read correctly from the JSON files.

## Root Cause
**Critical Bug Found in `parser.py` Line 254:**

The JSON hand history files use the field name `"value"` for bet/raise amounts:
```json
{
  "type": 7,
  "seat": 10,
  "value": 60
}
```

However, the parser was only looking for `"amount"`:
```python
amount = payload.get("amount", 0)  # ❌ Wrong - returns 0 for all events
```

This caused **ALL bet amounts to be read as 0**, making all the statistics meaningless.

## Fix Applied
Changed [parser.py:254](parser.py#L254) to check both field names:
```python
amount = payload.get("amount") or payload.get("value", 0)  # ✅ Correct
```

## Verification
Created `verify_extraction.py` which proves different files now produce different statistics:

| File | Hands | VPIP | PFR |
|------|-------|------|-----|
| poker-now-hands-game-pglTbRuizt7wXcuI2kmH2njXZ.json | 31 | 51.6% | 16.1% |
| poker-now-hands-game-pglHDu9aBaGvwAyHcgc-Lx3_3.json | 10 | 60.0% | 40.0% |
| poker-now-hands-game-pglgA-duz2_qg-O9P44jXqOdm.json | 101 | 58.4% | 17.8% |
| poker-now-hands-game-pglthZUPFQ_FqVSCfpHzl28b2.json | 10 | 60.0% | 10.0% |

Each file has a unique hash and produces different statistics, confirming the extraction is working correctly.

## Additional Improvements
1. **Enhanced Debugging**: Added file hash verification and detailed logging to `dashboard.py`
2. **Verification Script**: Created `verify_extraction.py` to validate data extraction
3. **Cache Clearing**: Removed `__pycache__` directories that could cause stale code issues

## How to Verify the Fix
Run the verification script:
```bash
python3 verify_extraction.py
```

Or run the dashboard with enhanced logging:
```bash
python3 dashboard.py charlie wyatt gabe --no-browser
```

You should now see:
- File fingerprints (hashes) showing files are different
- Different statistics for different hand history files
- Detailed extraction logs showing what's being analyzed

## Status
✅ **FIXED** - Data extraction is now working correctly. Different files produce different statistics as expected.
