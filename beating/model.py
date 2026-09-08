"""L2-regularized logistic residual correction to market log odds.

The market coefficient is fixed at one. Features/normalization fit on training
rows only. Calibration-only is the intercept special case.
"""
from dataclasses import dataclass
import numpy as np
from scipy.optimize import minimize
from scipy.special import expit, logit


def clipped(p):
    return np.clip(np.asarray(p, dtype=float), 1e-6, 1 - 1e-6)


def losses(y, p):
    y = np.asarray(y, dtype=float)
    p = clipped(p)
    return -(y * np.log(p) + (1-y) * np.log1p(-p))


@dataclass
class ResidualLogistic:
    penalty: float = 0.01

    def fit(self, x, y, market_p):
        x = np.asarray(x, dtype=float)
        if x.ndim != 2 or not np.isfinite(x).all():
            raise ValueError('Features must be a finite matrix')
        y = np.asarray(y, dtype=float)
        self.mean_ = x.mean(axis=0)
        self.scale_ = x.std(axis=0)
        self.scale_[self.scale_ < 1e-8] = 1
        z = np.column_stack([np.ones(len(x)), (x-self.mean_)/self.scale_])
        offset = logit(clipped(market_p))
        # Intercept receives weak regularization as well to stabilize small samples.
        weights = np.ones(z.shape[1]); weights[0] = 0.1
        def fun(beta):
            eta = offset + z @ beta
            value = np.mean(np.logaddexp(0, eta) - y*eta)
            value += self.penalty * np.sum(weights*beta**2) / 2
            grad = z.T @ (expit(eta)-y) / len(y) + self.penalty*weights*beta
            return value, grad
        result = minimize(fun, np.zeros(z.shape[1]), jac=True, method='L-BFGS-B',
                          options={'maxiter':1000,'ftol':1e-12,'gtol':1e-8})
        if not result.success:
            raise RuntimeError(f'Optimizer failed: {result.message}')
        self.coef_ = result.x
        return self

    def predict_proba(self, x, market_p):
        x = np.asarray(x, dtype=float)
        if x.ndim != 2 or not np.isfinite(x).all():
            raise ValueError('Features must be a finite matrix')
        z = np.column_stack([np.ones(len(x)), (x-self.mean_)/self.scale_])
        return expit(logit(clipped(market_p)) + z @ self.coef_)

    def to_dict(self):
        return {'penalty':self.penalty, 'mean':self.mean_.tolist(),
                'scale':self.scale_.tolist(),'coef':self.coef_.tolist()}

    @classmethod
    def from_dict(cls, value):
        model = cls(value['penalty'])
        model.mean_ = np.asarray(value['mean']); model.scale_ = np.asarray(value['scale'])
        model.coef_ = np.asarray(value['coef'])
        return model
