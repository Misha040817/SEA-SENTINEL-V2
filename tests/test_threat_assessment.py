import unittest
from datetime import datetime, timezone
from assessment import assess_vessel, AssessmentConfig
NOW = datetime(2026, 11, 2, 6, 0, tzinfo=timezone.utc)
BASE = dict(mmsi='533000001', timestamp='2026-11-02T05:59:00Z', latitude=3.0,
            longitude=101.0, sog_knots=12, restricted_zone_entry=False,
            route_deviation_nm=0, loitering_minutes=0, visual_ais_mismatch=False)
class AssessmentTests(unittest.TestCase):
    def test_low(self):
        self.assertEqual(assess_vessel(BASE, now=NOW)['risk_level'], 'Low')
    def test_high(self):
        row = {**BASE, 'restricted_zone_entry':True, 'route_deviation_nm':5, 'sog_knots':28}
        result = assess_vessel(row, now=NOW)
        self.assertEqual((result['risk_level'], result['score']), ('High',65))
    def test_stale_ais(self):
        result = assess_vessel({**BASE, 'timestamp':'2026-11-02T05:30:00Z'}, now=NOW)
        self.assertEqual(result['score'],15)
        self.assertEqual(result['indicators'][0]['code'],'ais_gap')
    def test_missing_not_low(self):
        self.assertEqual(assess_vessel({**BASE,'latitude':None},now=NOW)['risk_level'], 'Insufficient Data')
    def test_invalid_not_low(self):
        self.assertEqual(assess_vessel({**BASE,'sog_knots':-3},now=NOW)['risk_level'], 'Insufficient Data')
    def test_missing_ais_timestamp(self):
        self.assertEqual(assess_vessel({**BASE,'timestamp':None},now=NOW)['risk_level'], 'Insufficient Data')
    def test_zone_requires_coordinates(self):
        r=assess_vessel({**BASE,'latitude':None,'restricted_zone_entry':True},now=NOW)
        self.assertEqual(r['risk_level'],'Insufficient Data')
        self.assertTrue(r['data_errors'])
if __name__ == '__main__': unittest.main()
