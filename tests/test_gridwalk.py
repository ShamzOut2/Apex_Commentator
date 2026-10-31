import unittest

from apex.gridwalk import GridWalk, grid_order, parse_design, qualifying_times


class FakeClock:
    def __init__(self):
        self.t = 100.0

    def __call__(self):
        return self.t


DRIVERS = {i: {"number": str(n)} for i, n in [(1, "7"), (2, "12"), (3, "3"), (4, "99"), (5, "007")]}


class GridOrderTests(unittest.TestCase):
    def test_qualifying_results_first_then_the_rest_by_number(self):
        info = {"QualifyResultsInfo": {"Results": [
            {"Position": 1, "CarIdx": 4}, {"Position": 0, "CarIdx": 2}, {"Position": 2, "CarIdx": 99},
        ]}}
        order, source = grid_order(DRIVERS, info)
        # 99 is not in the session; 1, 3 and 5 had no qualifying result.
        self.assertEqual(order, [2, 4, 3, 5, 1])
        self.assertEqual(source, "qualifying")

    def test_falls_back_to_last_qualifying_session(self):
        info = {"SessionInfo": {"Sessions": [
            {"SessionType": "Practice", "ResultsPositions": [{"Position": 1, "CarIdx": 1}]},
            {"SessionType": "Lone Qualify", "ResultsPositions": [{"Position": 2, "CarIdx": 3}, {"Position": 1, "CarIdx": 5}]},
            {"SessionType": "Race", "ResultsPositions": None},
        ]}}
        order, source = grid_order(DRIVERS, info)
        self.assertEqual(order[:2], [5, 3])
        self.assertEqual(source, "qualifying session")

    def test_current_positions_then_car_number(self):
        order, source = grid_order(DRIVERS, {}, {1: 2, 2: 1, 3: 0})
        self.assertEqual((order[:2], source), ([2, 1], "current positions"))
        order, source = grid_order(DRIVERS, {})
        self.assertEqual((order, source), ([3, 5, 1, 2, 4], "car number"))

    def test_qualifying_times(self):
        info = {"QualifyResultsInfo": {"Results": [
            {"CarIdx": 1, "FastestTime": 88.5}, {"CarIdx": 2, "FastestTime": -1}, {"CarIdx": 3},
        ]}}
        self.assertEqual(qualifying_times(info), {1: 88.5})
        info = {"SessionInfo": {"Sessions": [{"SessionType": "Open Qualify", "ResultsPositions": [{"CarIdx": 4, "FastestTime": 90.1}]}]}}
        self.assertEqual(qualifying_times(info), {4: 90.1})
        self.assertEqual(qualifying_times({}), {})

    def test_parse_design(self):
        self.assertEqual(parse_design("12,ff0000,00FF00,0000ff"),
                         {"pattern": 12, "colors": ["#ff0000", "#00ff00", "#0000ff"]})
        self.assertEqual(parse_design("0,0,ffffff,777777,000000")["colors"], ["#ffffff", "#777777", "#000000"])
        self.assertIsNone(parse_design(""))
        self.assertIsNone(parse_design("3,notacolour"))


class GridWalkTests(unittest.TestCase):
    def setUp(self):
        self.clock = FakeClock()
        self.walk = GridWalk(interval=5, clock=self.clock)

    def test_advances_two_at_a_time_then_hides(self):
        self.walk.start()
        self.assertEqual((self.walk.visible, self.walk.running, self.walk.index), (True, True, 0))
        self.clock.t += 4.9
        self.assertFalse(self.walk.tick(5))
        self.clock.t += 0.2
        self.assertTrue(self.walk.tick(5))
        self.assertEqual(self.walk.index, 2)
        self.clock.t += 5
        self.walk.tick(5)
        self.assertEqual(self.walk.index, 4)  # last driver on their own
        self.clock.t += 5
        self.walk.tick(5)
        self.assertFalse(self.walk.visible)

    def test_loop(self):
        self.walk.configure(loop=True)
        self.walk.start(2)
        self.clock.t += 5
        self.walk.tick(4)
        self.assertEqual((self.walk.index, self.walk.visible), (0, True))

    def test_pause_keeps_time_already_spent(self):
        self.walk.start()
        self.clock.t += 3
        self.walk.pause()
        self.clock.t += 60
        self.assertFalse(self.walk.tick(6))
        self.assertEqual(self.walk.state()["elapsed"], 3)
        self.walk.resume()
        self.clock.t += 2.1
        self.assertTrue(self.walk.tick(6))
        self.assertEqual(self.walk.index, 2)

    def test_manual_steps_and_goto(self):
        self.walk.goto(5, 6)
        self.assertEqual(self.walk.index, 4)   # pairs start on even slots
        self.walk.step(1, 6)
        self.assertEqual(self.walk.index, 4)   # already the last pair
        self.walk.step(-1, 6)
        self.walk.step(-1, 6)
        self.walk.step(-1, 6)
        self.assertEqual(self.walk.index, 0)
        self.assertFalse(self.walk.running)    # stepping alone doesn't start the timer

    def test_settings_are_validated(self):
        self.walk.configure(interval=0.5)
        self.assertEqual(self.walk.interval, 2.0)
        self.walk.configure(interval=500)
        self.assertEqual(self.walk.interval, 120.0)

    def test_manual_order(self):
        keys = ["a", "b", "c"]
        self.walk.move(keys, "c", -1)
        self.assertEqual(self.walk.apply_order(keys), ["a", "c", "b"])
        # New drivers join at the back; ones who left drop out.
        self.assertEqual(self.walk.apply_order(["a", "b", "d"]), ["a", "b", "d"])
        self.assertEqual(self.walk.apply_order(["c", "b", "a", "d"]), ["a", "c", "b", "d"])
        self.walk.reset_order()
        self.assertEqual(self.walk.apply_order(keys), keys)
        with self.assertRaises(ValueError):
            self.walk.move(keys, "zz", 1)


if __name__ == "__main__":
    unittest.main()
