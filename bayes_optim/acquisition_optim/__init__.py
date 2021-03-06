from pdb import set_trace
import numpy as np
from typing import Callable, Any, Tuple, List, Union
from scipy.optimize import fmin_l_bfgs_b

from ..Solution import Solution
from .OnePlusOne_CMA import OnePlusOne_CMA, OnePlusOne_Cholesky_CMA
from .mies import MIES

__all__ = [
    'OnePlusOne_CMA', 'OnePlusOne_Cholesky_CMA', 'MIES', 'argmax_restart'
]

def argmax_restart(
    obj_fun: Callable,
    search_space,
    h: Callable = None,
    g: Callable = None,
    eval_type: str = 'list',
    eval_budget: int = 100,
    n_restart: int = 10,
    wait_iter: int = 3,
    optimizer: str = 'BFGS',
    logger = None
    ):
    # lists of the best solutions and acquisition values from each restart
    xopt, fopt = [], []
    best = -np.inf
    wait_count = 0

    # TODO: this part should be re-designed
    h_, g_ = h, g
    if eval_type == 'dict':
        var = search_space.var_name
        if h is not None:
            h_ = lambda x: h({k: x[i] for i, k in enumerate(var)})
        if g is not None:
            g_ = lambda x: g({k: x[i] for i, k in enumerate(var)})

    if (h is not None or g is not None) and optimizer == 'BFGS':
        optimizer = 'OnePlusOne_Cholesky_CMA'

    for iteration in range(n_restart):
        x0 = search_space.sampling(N=1, method='uniform')[0]

        # TODO: add constraint handling for BFGS
        if optimizer == 'BFGS':
            mask = np.nonzero(search_space.C_mask | search_space.O_mask)[0]
            bounds = np.array([search_space.bounds[i] for i in mask])

            if not all([isinstance(_, float) for _ in x0]):
                raise ValueError('BFGS is not supported with mixed variable types.')

            func = lambda x: tuple(map(lambda x: -1. * x, obj_fun(x)))
            xopt_, fopt_, stop_dict = fmin_l_bfgs_b(
                func, x0, pgtol=1e-8, factr=1e6,
                bounds=bounds, maxfun=eval_budget
            )

            xopt_ = xopt_.flatten().tolist()
            if not isinstance(fopt_, float):
                fopt_ = float(fopt_)
            fopt_ = -fopt_

            if logger is not None and stop_dict['warnflag'] != 0:
                logger.debug(
                    'L-BFGS-B terminated abnormally with the state: %s'%stop_dict
                )

        elif optimizer == 'OnePlusOne_Cholesky_CMA':
            lb, ub = list(zip(*search_space.bounds))
            opt = OnePlusOne_Cholesky_CMA(
                dim=search_space.dim, obj_fun=obj_fun,
                h=h_, g=g_, lb=lb, ub=ub, max_FEs=eval_budget,
                ftol=1e-4, xtol=1e-4, n_restart=0,
                minimize=False, verbose=False
            )
            xopt_, fopt_, stop_dict = opt.run()

            if 'FEs' in stop_dict:
                stop_dict['funcalls'] = stop_dict['FEs']
            else:
                stop_dict['funcalls'] = opt.eval_count

        elif optimizer == 'MIES':
            xopt_, fopt_, stop_dict = MIES(
                search_space, obj_fun, eq_func=h_, ineq_func=g_,
                max_eval=eval_budget, minimize=False,
                verbose=False, eval_type='list'
            ).optimize()

        if fopt_ > best:
            best = fopt_
            wait_count = 0

            if logger is not None:
                logger.debug(
                    'restart : %d - funcalls : %d - Fopt : %f'%(iteration + 1,
                    stop_dict['funcalls'], fopt_)
                )
        else:
            wait_count += 1

        eval_budget -= stop_dict['funcalls']
        xopt.append(xopt_)
        fopt.append(fopt_)

        if eval_budget <= 0 or wait_count >= wait_iter:
            break

    idx = np.argsort(fopt)[::-1]
    return xopt[idx[0]], fopt[idx[0]]