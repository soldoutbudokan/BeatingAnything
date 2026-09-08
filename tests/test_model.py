import unittest
import numpy as np
import pandas as pd
from beating.model import ResidualLogistic
from beating.evaluate import betting_returns


class ResearchTests(unittest.TestCase):
    def test_market_is_fixed_offset_and_serialization_roundtrip(self):
        market = np.array([.2,.3,.7,.8]*100)
        y = np.tile([0,0,1,1],100)
        x = np.empty((len(y),0))
        m = ResidualLogistic(.1).fit(x,y,market)
        np.testing.assert_allclose(m.predict_proba(x,market),market,atol=1e-8)
        clone = ResidualLogistic.from_dict(m.to_dict())
        np.testing.assert_allclose(clone.predict_proba(x,market),market,atol=1e-8)

    def test_flat_stakes_settlement_and_vig_filter(self):
        frame = pd.DataFrame({'fd_home_open_decimal':[2.,2.,1.8],
                              'fd_away_open_decimal':[1.91,1.91,1.8],
                              'home_win':[1,0,1]})
        result = betting_returns(frame,[.6,.6,.9])
        np.testing.assert_array_equal(result['selected'],[True,True,False])
        np.testing.assert_allclose(result['profit'],[1.,-1.,0.])
        np.testing.assert_allclose(result['haircut_profit'],[.98,-1.,0.])

    def test_nonfinite_input_rejected(self):
        with self.assertRaises(ValueError):
            ResidualLogistic().fit([[float('nan')]], [1], [.5])


if __name__ == '__main__': unittest.main()
