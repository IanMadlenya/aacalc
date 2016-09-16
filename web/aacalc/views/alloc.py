# AACalc - Asset Allocation Calculator
# Copyright (C) 2009, 2011-2016 Gordon Irlam
#
# This program is free software: you can redistribute it and/or modify
# it under the terms of the GNU Affero General Public License as published by
# the Free Software Foundation, either version 3 of the License, or
# (at your option) any later version.
#
# This program is distributed in the hope that it will be useful,
# but WITHOUT ANY WARRANTY; without even the implied warranty of
# MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
# GNU Affero General Public License for more details.
#
# You should have received a copy of the GNU Affero General Public License
# along with this program.  If not, see <http://www.gnu.org/licenses/>.

from datetime import datetime, timedelta
from decimal import Decimal
from math import ceil, exp, isnan, log, sqrt
from os import umask
from tempfile import mkdtemp

from django.forms.forms import NON_FIELD_ERRORS
from django.forms.utils import ErrorList
from django.shortcuts import render
from numpy import array
from numpy.linalg import inv, LinAlgError
from scipy.stats import lognorm, norm
from subprocess import check_call

from aacalc.forms import AllocAaForm, AllocNumberForm
from aacalc.spia import LifeTable, Scenario, YieldCurve
from settings import ROOT, STATIC_ROOT, STATIC_URL

mwr = 1.0
    # Observed real MWRs were in this range for ages 40-80. At age 85 it was 9% lower when using aer2005-08-summary.
    # No adjustment for state taxes, but we impose a minimum required total portfolio gain of 4% later.

# Deleterious stock market returns are fat-tailed.
# For 1927-2014 we empirically observed the 10th percentile stock return corresponding to the 6th percentile of the lognormal distribution.
loss_pctl = 0.1
loss_pctl_fat_tail = 0.06
# Deleterious bond market returns appear, if anything, the opposite of fat-tailed.
# We could try to weight this in, but don't. It is acceptable to over-report the odds of deleterious outcomes.

annuitization_delay_cost = (0.0, 0.0, 0.0, 0.013, 0.018, 0.029, 0.049, 0.093, 0.221, 0.391)
    # Cost of delaying anuitization by 10 years, every 10 years of age.
    # Birth year = 2015 - starting age.

# Next two parameters determined to give good results empirically
# using stochastic dynamic programming as the reference. Don't know
# any other good way to approach the problem.
consume_pctl = 97
    # Percentile age up to which to use in computing amount to
    # consume.
growth_pctl_no_db = 43
    # Percentile location of fixed rate of return to use in computing
    # amount to consume in absence of defined benefits.

# No enums until Python 3.4.
stocks_index = 0
bonds_index = 1
contrib_index = 2
risk_free_index = 3
existing_annuities_index = 4
new_annuities_index = 5
num_index = 6

class Alloc:

    class IdenticalCovarError(Exception):
        pass

    def default_alloc_params(self):

        return {
            'sex': 'male',
            'age': 50,
            'sex2': 'none',
            'age2': None,
            'le_set': None,
            'le_set2': None,

            'db' : ({
                'social_security': True,
                'who': 'self',
                'age': 66,
                'amount': 15000,
                'inflation_indexed': True,
                'period_certain': 0,
                'joint_type': 'survivor',
                'joint_payout_pct': 0,
            }, {
                'social_security': True,
                'who': 'spouse',
                'age': 66,
                'amount': 0,
                'inflation_indexed': True,
                'period_certain': 0,
                'joint_type': 'survivor',
                'joint_payout_pct': 0,
            }, {
                'social_security': False,
                'description': 'Pension',
                'who': 'self',
                'age': 66,
                'amount': 0,
                'inflation_indexed': True,
                'period_certain': 0,
                'joint_type': 'survivor',
                'joint_payout_pct': 0,
            }, {
                'social_security': False,
                'description': 'Pension',
                'who': 'self',
                'age': 66,
                'amount': 0,
                'inflation_indexed': True,
                'period_certain': 0,
                'joint_type': 'survivor',
                'joint_payout_pct': 0,
            }, {
                'social_security': False,
                'description': 'Pension',
                'who': 'spouse',
                'age': 66,
                'amount': 0,
                'inflation_indexed': True,
                'period_certain': 0,
                'joint_type': 'survivor',
                'joint_payout_pct': 0,
            }, {
                'social_security': False,
                'description': 'Pension',
                'who': 'spouse',
                'age': 66,
                'amount': 0,
                'inflation_indexed': True,
                'period_certain': 0,
                'joint_type': 'survivor',
                'joint_payout_pct': 0,
            }, {
                'social_security': False,
                'description': 'Income annuity',
                'who': 'self',
                'age': 66,
                'amount': 0,
                'inflation_indexed': True,
                'period_certain': 0,
                'joint_type': 'contingent',
                'joint_payout_pct': 70,
            }, {
                'social_security': False,
                'description': 'Income annuity',
                'who': 'self',
                'age': 66,
                'amount': 0,
                'inflation_indexed': False,
                'period_certain': 0,
                'joint_type': 'contingent',
                'joint_payout_pct': 70,
            }, {
                'social_security': False,
                'description': 'Income annuity',
                'who': 'spouse',
                'age': 66,
                'amount': 0,
                'inflation_indexed': True,
                'period_certain': 0,
                'joint_type': 'contingent',
                'joint_payout_pct': 70,
            }, {
                'social_security': False,
                'description': 'Income annuity',
                'who': 'spouse',
                'age': 66,
                'amount': 0,
                'inflation_indexed': False,
                'period_certain': 0,
                'joint_type': 'contingent',
                'joint_payout_pct': 70,
            }),
            'p_traditional_iras': 0,
            'tax_rate_pct': 30,
            'p_roth_iras': 0,
            'p': 0,
            'contribution': 2000,
            'contribution_growth_pct': Decimal('7.0'),
            'contribution_vol_pct': Decimal('10.0'),
            'equity_contribution_corr_pct': Decimal('0.0'),
            'bonds_contribution_corr_pct': Decimal('0.0'),

            'retirement_age': 66,
            'joint_income_pct': 70,
            'required_income': None,
            'desired_income': None,
            'purchase_income_annuity': True,
            'use_lm_bonds': True,

            'equity_ret_pct': Decimal('7.2'),
            'equity_vol_pct': Decimal('17.0'),
            'bonds_ret_pct': Decimal('0.0'),
            'bonds_vol_pct': Decimal('8.7'),
            'equity_bonds_corr_pct': Decimal('7.3'),
            'real_vol_10yr_pct': Decimal('4.9'),
            'bonds_lm_bonds_corr_short_pct': Decimal('28.9'),
            'equity_se_pct': Decimal('1.7'),
            'confidence_pct': 80,
            'expense_pct': Decimal('0.1'),
            'date': (datetime.utcnow() + timedelta(hours = -24)).date().isoformat(),  # Yesterday's quotes are retrieved at midnight.

            'gamma': Decimal('3.0'),
            'risk_tolerance_pct': Decimal('20.0'),
        }

    def distribution_pctl(self, pctl, mean, vol):
        # Convert mean and vol to lognormal distribution mu and sigma parameters.
        try:
            mu = log(mean ** 2 / sqrt(vol ** 2 + mean ** 2))
        except ZeroDivisionError:
            return mean
        sigma = sqrt(log(vol ** 2 / mean ** 2 + 1))
        value = lognorm.ppf(pctl, sigma, scale=exp(mu))
        value = float(value) # De-numpyfy.
        if isnan(value):
            # vol == 0.
            return mean
        return value

    def geomean(self, mean, vol):
        return self.distribution_pctl(0.5, mean, vol)

    def solve_merton(self, gamma, sigma_matrix, alpha, r):
        try:
            w = inv(sigma_matrix).dot(array(alpha) - r) / gamma
        except LinAlgError:
            raise self.IdenticalCovarError
        return tuple(float(wi) for wi in w) # De-numpyfy.

    def stochastic_schedule(self, mean, years = None):

        def sched(y):
            if years == None or y < years:
                return mean ** y
            else:
                return 0

        return sched

    def npv_contrib(self, ret):
        payout_delay = 0
        schedule = self.stochastic_schedule(1.0 + ret, self.pre_retirement_years)
        scenario = Scenario(self.yield_curve_real, payout_delay, None, None, 0, self.life_table_120, life_table2 = self.life_table_120, \
            joint_payout_fraction = 1, joint_contingent = True, period_certain = self.period_certain, \
            frequency = 1, cpi_adjust = 'all', schedule = schedule)
            # Table used is irrelevant. Choose for speed.
        value = self.contribution * scenario.price()
        annual_ret = scenario.annual_return
        return value, annual_ret

    def value_table_db(self, life_table, life_table2):

        table_db = []
        nv_db = 0

        for db in self.db:

            amount = float(db['amount'])

            if amount == 0:
                continue

            yield_curve = self.yield_curve_real if db['inflation_indexed'] else self.yield_curve_nominal

            if db['who'] == 'self':
                starting_age = self.age
                lt1 = life_table
                lt2 = life_table2
            else:
                starting_age = self.age2
                lt1 = life_table2
                lt2 = life_table

            delay = float(db['age']) - starting_age
            positive_delay = max(0, delay)
            negative_delay = min(0, delay)
            payout_delay = positive_delay * 12
            period_certain = max(0, self.period_certain - positive_delay, float(db['period_certain']) + negative_delay)
            joint_payout_fraction = float(db['joint_payout_pct']) / 100
            joint_contingent = (db['joint_type'] == 'contingent')

            scenario = Scenario(yield_curve, payout_delay, None, None, 0, lt1, life_table2 = lt2, \
                joint_payout_fraction = joint_payout_fraction, joint_contingent = joint_contingent, \
                period_certain = period_certain, frequency = self.frequency, cpi_adjust = self.cpi_adjust)
            price = scenario.price() * amount
            nv_db += price

            table_db.append({
                'description': db['description'] if db['description'] else 'Social Security',
                'who': db['who'],
                'nv': '{:,.0f}'.format(price),
            })

        return table_db, nv_db

    def value_table(self, nv_db, taxable):

        results = {}
        display = {}

        nv_traditional = self.traditional * (1 - self.tax_rate)
        nv_investments = nv_traditional + self.npv_roth + taxable
        nv = nv_db + nv_investments + self.nv_contributions

        results['nv_db'] = nv_db
        results['nv'] = nv

        display['nv_db'] = '{:,.0f}'.format(nv_db)
        display['nv_traditional'] = '{:,.0f}'.format(nv_traditional)
        display['nv_roth'] = '{:,.0f}'.format(self.npv_roth)
        display['nv_taxable'] = '{:,.0f}'.format(taxable)
        display['nv_investments'] = '{:,.0f}'.format(nv_investments)
        display['nv_contributions'] = '{:,.0f}'.format(self.nv_contributions)
        display['nv'] = '{:,.0f}'.format(nv)
        display['ret_contributions'] = '{:.1f}'.format(self.ret_contributions * 100)

        return results, display

    def statistics(self, w, rets, equity_vol, bonds_vol, lm_bonds_vol, cov_ec2, cov_bc2, cov_eb2, cov_bl2):

        total_ret = w[contrib_index] * rets[contrib_index] + w[stocks_index] * rets[stocks_index] + w[bonds_index] * rets[bonds_index] + \
            w[risk_free_index] * rets[risk_free_index] + w[existing_annuities_index] * rets[existing_annuities_index] + \
            w[new_annuities_index] * rets[new_annuities_index]

        total_var = w[contrib_index] ** 2 * self.contribution_vol ** 2 + \
            w[stocks_index] ** 2 * equity_vol ** 2 + \
            w[bonds_index] ** 2 * bonds_vol ** 2 + \
            w[risk_free_index] ** 2 * lm_bonds_vol ** 2 + \
            2 * w[contrib_index] * w[stocks_index] * cov_ec2 + \
            2 * w[contrib_index] * w[bonds_index] * cov_bc2 + \
            2 * w[stocks_index] * w[bonds_index] * cov_eb2 + \
            2 * w[bonds_index] * w[risk_free_index] * cov_bl2
            # risk_free covariance assumed zero against other asset classes.
        total_vol = sqrt(total_var)

        total_geometric_ret = self.geomean(1 + total_ret, total_vol) - 1

        return total_ret, total_vol, total_geometric_ret

    def investment_statistics(self, w, rets, equity_vol, cov_ec2, cov_bc2, cov_eb2):

        cov_bl2_short = self.bonds_vol_short * self.lm_bonds_vol_short * self.bonds_lm_bonds_corr_short ** 2

        w_investments = self.non_annuitized_weights(w, no_contrib=True)

        return self.statistics(w_investments, rets, equity_vol, self.bonds_vol_short, self.lm_bonds_vol_short, cov_ec2, cov_bc2, cov_eb2, cov_bl2_short)

    def consume_factor(self, ret):

        # We should use total_var, total_vol, and gamma to compute the
        # annual consumption amount.  Merton's Continuous Time Finance
        # provides solutions for a single risky asset with a finite
        # time horizon, and many asset with a infinite time horizon,
        # but not many assets with a finite time horizon. And even if
        # such a solution existed we would also need to factor in
        # pre-retirement years.

        # We compute the withdrawal amount for a fixed compounding
        # total portfolio.
        schedule = self.stochastic_schedule(1 / (1.0 + ret))
        scenario = Scenario(self.yield_curve_zero, self.payout_delay, None, None, 0, self.life_table, life_table2 = self.life_table2, \
            joint_payout_fraction = self.joint_payout_fraction, joint_contingent = True, \
            period_certain = 0, frequency = self.frequency, cpi_adjust = self.cpi_adjust, percentile = consume_pctl, schedule = schedule)
        c_factor = 1.0 / scenario.price()

        return c_factor

    def non_annuitized_weights(self, w, no_contrib=False):

        w = list(w)
        if no_contrib:
            w[contrib_index] = 0
        w[existing_annuities_index] = 0
        w[new_annuities_index] = 0
        s = sum(w)
        try:
            return list(wi / float(s) for wi in w)
        except:
            return [0] * len(w)


    def risk_limit(self, use_lm_bonds, w_init, rets, results, equity_vol, bonds_vol, lm_bonds_vol, cov_ec2, cov_bc2, cov_eb2, cov_bl2):
        # Ideally would scale back using mean-variance optimization, but given the limited number of asset classes, this is good enough.

        found_loss = None
        low = -1
        high = 1
        for _ in range(50):

            if high - low < 0.0001:
                break

            mid = (high + low) / 2.0

            w = list(w_init)
            adjust = mid * w[stocks_index]
            w[stocks_index] -= adjust
            w[risk_free_index] += adjust

            if not use_lm_bonds:
                w[bonds_index] += w[risk_free_index]
                w[risk_free_index] = 0

            investments_ret, investments_vol, investments_geometric_ret = self.investment_statistics(w, rets, equity_vol, cov_ec2, cov_bc2, cov_eb2)

            investments_loss = 1 - self.distribution_pctl(loss_pctl_fat_tail, 1 + investments_ret, investments_vol)

            if found_loss == None:
                found_loss = investments_loss
                found_w = w

            if investments_loss <= self.risk_tolerance or self.risk_tolerance < investments_loss < found_loss:

                found_loss = investments_loss
                found_w = w

                if mid == 0:
                    break

                high = mid

            else:

                low = mid

        investments_loss = found_loss
        w = found_w

        ret, vol, geometric_ret = self.statistics(self.non_annuitized_weights(w), rets, equity_vol, bonds_vol, lm_bonds_vol, \
            cov_ec2, cov_bc2, cov_eb2, cov_bl2)
        alloc_db = w[existing_annuities_index] + w[new_annuities_index]
        growth_pctl = (1 - alloc_db) * growth_pctl_no_db / 100.0 + alloc_db * 0.5
            # The greater the defined benefits cushion the greater the growth rate that can be assumed for non-defined benefits.
        growth_rate = self.distribution_pctl(growth_pctl, 1 + ret, vol) - 1
        c_factor = self.consume_factor(growth_rate)
        consume = results['nv'] * (w[existing_annuities_index] / self.discounted_retirement_le + \
                                   w[new_annuities_index] * mwr / self.discounted_retirement_le_annuity + \
                                   (1 - alloc_db) * c_factor)

        return w, consume, investments_loss

    def fix_allocs(self, mode, w_prime, rets, results, annuitize, equity_vol, bonds_vol, lm_bonds_vol, cov_ec2, cov_bc2, cov_eb2, cov_bl2):

        purchase_income_annuity = any(a > 0 for a in annuitize)

        w_fixed = [0] * num_index
        w_fixed[stocks_index] = min(max(0, w_prime[stocks_index] * (1 - annuitize[stocks_index])), 1)
        w_fixed[bonds_index] = min(max(0, w_prime[bonds_index] * (1 - annuitize[bonds_index])), 1)
        w_fixed[risk_free_index] = min(max(0, w_prime[risk_free_index] * (1 - annuitize[risk_free_index])), 1)
        try:
            w_fixed[contrib_index] = self.nv_contributions / results['nv']
        except ZeroDivisionError:
            w_fixed[contrib_index] = 1

        alloc_db = 1 - sum(w_fixed)
        try:
            w_fixed[existing_annuities_index] = results['nv_db'] / results['nv']
        except ZeroDivisionError:
            w_fixed[existing_annuities_index] = 0
        if self.required_income != None:
            try:
                required_safe = self.discounted_retirement_le_annuity / mwr * \
                    (self.required_income / results['nv'] - w_fixed[existing_annuities_index] / self.discounted_retirement_le)
            except ZeroDivisionError:
                required_safe = 0
            required_safe += w_fixed[existing_annuities_index]
            required_safe = min(max(0, required_safe), 1 - w_fixed[contrib_index])
        else:
            required_safe = 0
        if purchase_income_annuity:
            target_alloc_db = max(w_fixed[existing_annuities_index], required_safe, alloc_db)
        else:
            target_alloc_db = w_fixed[existing_annuities_index]
        surplus = alloc_db - target_alloc_db
        alloc_db = target_alloc_db
        w_fixed[risk_free_index] += surplus
        w_fixed[new_annuities_index] = max(0, alloc_db - w_fixed[existing_annuities_index]) # Eliminate negative values from fp rounding errors.
        target_risk_free = min(max(0, w_fixed[risk_free_index], required_safe - alloc_db), 1)
        surplus = w_fixed[risk_free_index] - target_risk_free
        w_fixed[risk_free_index] = target_risk_free
        w_fixed[bonds_index] += surplus
        target_bonds = min(max(0, w_fixed[bonds_index]), 1)
        surplus = w_fixed[bonds_index] - target_bonds
        w_fixed[bonds_index] = target_bonds
        w_fixed[stocks_index] += surplus
        w_fixed[stocks_index] = max(0, w_fixed[stocks_index]) # Eliminate negative values from fp rounding errors.

        for count in range(2):

            w_try = list(w_fixed)
            w_fixed, consume, loss = self.risk_limit(False, w_try, rets, results, equity_vol, bonds_vol, lm_bonds_vol, cov_ec2, cov_bc2, cov_eb2, cov_bl2)

            if self.use_lm_bonds:
                w_fixed_lm, consume_lm, loss_lm = self.risk_limit(True, w_try, rets, results, equity_vol, bonds_vol, lm_bonds_vol, \
                    cov_ec2, cov_bc2, cov_eb2, cov_bl2)
                if consume_lm >= consume and (loss_lm <= self.risk_tolerance or loss_lm <= loss):
                    w_fixed, consume, loss = w_fixed_lm, consume_lm, loss_lm

            if count == 1 or mode == 'number' or self.desired_income == None or consume <= self.desired_income:
                break

            ratio = self.desired_income / consume

            w_fixed = list(w_try)
            w_fixed[bonds_index] *= ratio
            w_risk_free_all = w_fixed[risk_free_index] + w_fixed[existing_annuities_index] + w_fixed[new_annuities_index]
            w_risk_free_new = max(0, max(w_risk_free_all * ratio, required_safe) - w_fixed[existing_annuities_index])
            w_annuitize = max(0, w_risk_free_all * annuitize[risk_free_index] - w_fixed[existing_annuities_index])
            w_fixed[new_annuities_index] = min(w_risk_free_new, w_annuitize)
            w_fixed[risk_free_index] = w_risk_free_new - w_fixed[new_annuities_index]
            w_fixed[stocks_index] = 0
            w_fixed[stocks_index] = 1 - sum(w_fixed)
            w_fixed[stocks_index] = max(0, w_fixed[stocks_index]) # Eliminate negative values from fp rounding errors.

        assert(all(w >= 0 for w in w_fixed))
        assert(abs(sum(w_fixed) - 1) < 1e-15)

        total_ret, total_vol, total_geometric_ret = self.statistics(w_fixed, rets, equity_vol, bonds_vol, lm_bonds_vol, cov_ec2, cov_bc2, cov_eb2, cov_bl2)

        return w_fixed, consume, total_ret, total_vol, total_geometric_ret

    def calc_scenario(self, mode, description, factor, data, results, force_annuitize):

        rets = [0] * num_index
        expense = float(data['expense_pct']) / 100
        rets[stocks_index] = float(data['equity_ret_pct']) / 100 - expense
        rets[stocks_index] += factor * float(data['equity_se_pct']) / 100
        rets[bonds_index] = float(data['bonds_ret_pct']) / 100 - expense
        rets[contrib_index] = self.ret_contributions
        rets[risk_free_index] = self.lm_bonds_ret
        rets[existing_annuities_index] = self.lm_bonds_ret
        rets[new_annuities_index] = self.lm_bonds_ret

        gamma = float(data['gamma'])
        equity_vol = float(data['equity_vol_pct']) / 100
        bonds_vol = float(data['bonds_vol_pct']) / 100
        lm_bonds_vol = 0

        equity_gm = self.geomean(1 + rets[stocks_index], equity_vol) - 1
        bonds_gm = self.geomean(1 + rets[bonds_index], bonds_vol) - 1

        equity_bonds_corr = float(data['equity_bonds_corr_pct']) / 100
        cov_ec2 = equity_vol * self.contribution_vol * self.equity_contribution_corr ** 2
        cov_bc2 = bonds_vol * self.contribution_vol * self.bonds_contribution_corr ** 2
        cov_eb2 = equity_vol * bonds_vol * equity_bonds_corr ** 2
        cov_bl2 = 0

        if mode == 'aa' and self.contribution_vol > 0: # Avoid contribution_vol == 0 as covariance matrix inverse fails becasue matrix is singular.
            lo = -0.5
            hi = 0.5
            for _ in range(50):
                future_growth_try = (lo + hi) / 2.0
                sigma_matrix = (
                    (equity_vol ** 2, cov_eb2, cov_ec2),
                    (cov_eb2, bonds_vol ** 2, cov_bc2),
                    (cov_ec2, cov_bc2, self.contribution_vol ** 2)
                )
                alpha = (rets[stocks_index], rets[bonds_index], future_growth_try)
                w = list(self.solve_merton(gamma, sigma_matrix, alpha, self.lm_bonds_ret))
                w.append(1 - sum(w))
                discounted_contrib, _ = self.npv_contrib((1 + self.contribution_growth) / (1 + future_growth_try) - 1)
                npv_discounted = results['nv'] - self.nv_contributions + discounted_contrib
                try:
                    wc_discounted = discounted_contrib / npv_discounted
                except ZeroDivisionError:
                    wc_discounted = 0
                if hi - lo < 0.000001:
                    break
                if wc_discounted > w[contrib_index]:
                    lo = future_growth_try
                else:
                    hi = future_growth_try
            try:
                w_prime = list(wi * npv_discounted / results['nv'] for wi in w)
            except ZeroDivisionError:
                w_prime = list(0 for _ in w)
            w_prime[contrib_index] = 0
            w_prime[contrib_index] = 1 - sum(w_prime)
        else:
            future_growth_try = 0
            discounted_contrib, _ = self.npv_contrib(self.contribution_growth)
            try:
                wc_discounted = discounted_contrib / results['nv']
            except ZeroDivisionError:
                wc_discounted = 0
            sigma_matrix = (
                (equity_vol ** 2, cov_eb2),
                (cov_eb2, bonds_vol ** 2),
            )
            alpha = (rets[stocks_index], rets[bonds_index])
            w = list(self.solve_merton(gamma, sigma_matrix, alpha, self.lm_bonds_ret))
            w.append(wc_discounted)
            w.append(1 - sum(w))
            w_prime = list(w)
        w_prime = list(max(0, wi) for wi in w_prime)
        w_prime[risk_free_index] = 0
        w_prime[risk_free_index] = 1 - sum(w_prime)

        annuitize = [0] * num_index
        w_fixed, consume, total_ret, total_vol, total_geometric_ret = \
            self.fix_allocs(mode, w_prime, rets, results, annuitize, equity_vol, bonds_vol, lm_bonds_vol, cov_ec2, cov_bc2, cov_eb2, cov_bl2)
        consume_unannuitize = consume

        if data['purchase_income_annuity']:

            annuitize[stocks_index] = min(max(0, (self.min_age - 65.0) / (90 - 65)), 1)
            # Don't have a good handle on when to annuitize regular
            # bonds.  Results are from earlier work in which bonds
            # returned 3.1 +/- 11.9% based on historical data.  These
            # returns are unlikely to be repeated in the forseeable
            # future.
            annuitize[bonds_index] = min(max(0, (self.min_age - 30.0) / (60 - 30)), 1)
            annuitize_lm_bonds_age = min(max(40, 40 + (self.retirement_age - self.age + self.min_age - 50) / 2.0), 50)
            annuitize[risk_free_index] = 0 if self.min_age < annuitize_lm_bonds_age else 1

            w_fixed_annuitize, consume_annuitize, total_ret_annuitize, total_vol_annuitize, total_geometric_ret_annuitize = \
                self.fix_allocs(mode, w_prime, rets, results, annuitize, equity_vol, bonds_vol, lm_bonds_vol, cov_ec2, cov_bc2, cov_eb2, cov_bl2)

            annuitize_gain = consume_annuitize - consume_unannuitize
            purchase_income_annuity = results['nv'] * w_fixed_annuitize[new_annuities_index]

            use_age = self.min_age - 5 # Delay cost estimates look forward for 10 years.
            index = min(int(use_age / 10.0), len(annuitization_delay_cost))
            next_index = min(int((use_age + 10) / 10.0), len(annuitization_delay_cost))
            cost_low = annuitization_delay_cost[index] / 10
            cost_high = annuitization_delay_cost[next_index] / 10
            weight = (use_age % 10) / 10.0
            cost = (1 - weight) * cost_low + weight * cost_high
            delay_fraction_cost = cost * w_fixed_annuitize[new_annuities_index]
            annuitize_delay_cost = results['nv'] * delay_fraction_cost

            if force_annuitize == None:
                annuitize_plan = annuitize_gain > 0.04 * consume_unannuitize and delay_fraction_cost > 0.001
            else:
                annuitize_plan = force_annuitize
            if annuitize_plan:
                w_fixed, consume, total_ret, total_vol, total_geometric_ret = \
                    w_fixed_annuitize, consume_annuitize, total_ret_annuitize, total_vol_annuitize, total_geometric_ret_annuitize

        else:

            annuitize_plan = False
            consume_annuitize = 0
            annuitize_gain = 0
            purchase_income_annuity = 0
            annuitize_delay_cost = 0

        investments_ret, investments_vol, investments_geometric_ret = self.investment_statistics(w_fixed, rets, equity_vol, cov_ec2, cov_bc2, cov_eb2)

        w_fixed_investments = w_fixed[stocks_index] + w_fixed[bonds_index] + w_fixed[risk_free_index]

        investments_loss = 1 - self.distribution_pctl(loss_pctl_fat_tail, 1 + investments_ret, investments_vol)
        total_loss = 1 - self.distribution_pctl(loss_pctl_fat_tail, 1 + total_ret, total_vol)

        try:
            aa_equity = w_fixed[stocks_index] / w_fixed_investments
        except ZeroDivisionError:
            aa_equity = 1
        aa_bonds = 1 - aa_equity

        result = {
            'description': description,
            'lm_bonds_ret_pct': '{:.1f}'.format(self.lm_bonds_ret * 100),
            'lm_bonds_duration': '{:.1f}'.format(self.lm_bonds_duration),
            'retirement_life_expectancy': '{:.1f}'.format(self.retirement_le),
            'consume': '{:,.0f}'.format(consume),
            'equity_am_pct':'{:.1f}'.format(rets[stocks_index] * 100),
            'bonds_am_pct':'{:.1f}'.format(rets[bonds_index] * 100),
            'equity_gm_pct':'{:.1f}'.format(equity_gm * 100),
            'bonds_gm_pct':'{:.1f}'.format(bonds_gm * 100),
            'future_growth_try_pct': '{:.1f}'.format(future_growth_try * 100),
            'w' : [{
                'name' : 'Discounted future contributions',
                'alloc': '{:.0f}'.format(w[contrib_index] * 100),
            }, {
                'name': 'Stocks',
                'alloc': '{:.0f}'.format(w[stocks_index] * 100),
            }, {
                'name': 'Regular bonds',
                'alloc': '{:.0f}'.format(w[bonds_index] * 100),
            }, {
                'name': 'Liability matching bonds and defined benefits',
                'alloc': '{:.0f}'.format(w[risk_free_index] * 100),
            }],
            'discounted_contrib': '{:,.0f}'.format(discounted_contrib),
            'wc_discounted':  '{:.0f}'.format(wc_discounted * 100),
            'w_prime' : [{
                'name' : 'Future contributions',
                'alloc': '{:.0f}'.format(w_prime[contrib_index] * 100),
            }, {
                'name': 'Stocks',
                'alloc': '{:.0f}'.format(w_prime[stocks_index] * 100),
            }, {
                'name': 'Regular bonds',
                'alloc': '{:.0f}'.format(w_prime[bonds_index] * 100),
            }, {
                'name': 'Liability matching bonds and defined benefits',
                'alloc': '{:.0f}'.format(w_prime[risk_free_index] * 100),
            }],
            'annuitize_equity_pct': '{:.0f}'.format(annuitize[stocks_index] * 100),
            'annuitize_bonds_pct': '{:.0f}'.format(annuitize[bonds_index] * 100),
            'annuitize_lm_bonds_pct': '{:.0f}'.format(annuitize[risk_free_index] * 100),
            'annuitize_gain': '{:,.0f}'.format(annuitize_gain),
            'annuitize_delay_cost': '{:,.0f}'.format(annuitize_delay_cost),
            'alloc_equity_pct': '{:.0f}'.format(w_fixed[stocks_index] * 100),
            'alloc_bonds_pct': '{:.0f}'.format(w_fixed[bonds_index] * 100),
            'alloc_lm_bonds_pct': '{:.0f}'.format(w_fixed[risk_free_index] * 100),
            'alloc_contributions_pct': '{:.0f}'.format(w_fixed[contrib_index] * 100),
            'alloc_existing_db_pct': '{:.0f}'.format(w_fixed[existing_annuities_index] * 100),
            'alloc_new_db_pct': '{:.0f}'.format(w_fixed[new_annuities_index] * 100),
            'alloc_investments_pct': '{:.0f}'.format(w_fixed_investments * 100),
            'consume_annuitize': '{:,.0f}'.format(consume_annuitize),
            'consume_unannuitize': '{:,.0f}'.format(consume_unannuitize),
            'purchase_income_annuity': '{:,.0f}'.format(purchase_income_annuity),
            'aa_equity_pct': '{:.0f}'.format(aa_equity * 100),
            'aa_bonds_pct': '{:.0f}'.format(aa_bonds * 100),
            'equity_ret_pct': '{:.1f}'.format(rets[stocks_index] * 100),
            'bonds_ret_pct': '{:.1f}'.format(rets[bonds_index] * 100),
            'lm_bonds_vol_short_pct': '{:.1f}'.format(self.lm_bonds_vol_short * 100),
            'investments_ret_pct': '{:.1f}'.format(investments_ret * 100),
            'investments_vol_pct': '{:.1f}'.format(investments_vol * 100),
            'investments_geometric_ret_pct': '{:.1f}'.format(investments_geometric_ret * 100),
            'total_ret_pct': '{:.1f}'.format(total_ret * 100),
            'total_vol_pct': '{:.1f}'.format(total_vol * 100),
            'total_geometric_ret_pct': '{:.1f}'.format(total_geometric_ret * 100),
            'loss_pctl_pct': '{:.0f}'.format(loss_pctl * 100),
            'investments_loss_pct': '{:.1f}'.format(investments_loss * 100),
            'total_loss_pct': '{:.1f}'.format(total_loss * 100),
            'annuitize_plan': annuitize_plan,
            'consume_value': consume,
            'w_fixed': w_fixed,
            'aa_equity': aa_equity,
            'aa_bonds': aa_bonds,
        }

        if mode == 'number':
            result['w'].pop(0)
            result['w_prime'].pop(0)

        return result

    def calc(self, mode, description, factor, data, results, display, force_annuitize):

        if mode == 'aa':

            calc_result = self.calc_scenario(mode, description, factor, data, results, force_annuitize)

        else:

            results = dict(results)
            nv = results['nv']
            max_portfolio = self.desired_income * (120 - self.min_age - self.pre_retirement_years)
            found_location = None # Consume may have a discontinuity due to annuitization; be sure to return a location that meets or exceeds the requirement.
            found_value = None
            low = 0
            high = max_portfolio
            for _ in range(50):
                mid = (low + high) / 2.0
                # Hack the table rather than recompute for speed.
                results['nv'] = nv + mid
                calc_scenario = self.calc_scenario(mode, description, factor, data, results, force_annuitize)
                if calc_scenario['consume_value'] >= self.desired_income or not found_location:
                    found_location = mid
                    found_value = calc_scenario
                if high - low < 0.000001 * max_portfolio:
                    break
                if calc_scenario['consume_value'] < self.desired_income:
                    low = mid
                else:
                    high = mid

            found_value['taxable'] = found_location

            _, display = self.value_table(self.nv_db, found_location) # Recompute.

            calc_result = found_value

        calc_result['npv_display'] = display

        return calc_result

    def compute_results(self, data, mode):

        results = {}

        self.date_str = data['date']
        self.yield_curve_real = YieldCurve('real', self.date_str)
        self.yield_curve_nominal = YieldCurve('nominal', self.date_str)
        self.yield_curve_zero = YieldCurve('fixed', self.date_str)

        if self.yield_curve_real.yield_curve_date == self.yield_curve_nominal.yield_curve_date:
            results['yield_curve_date'] = self.yield_curve_real.yield_curve_date;
        else:
            results['yield_curve_date'] = self.yield_curve_real.yield_curve_date + ' real, ' + \
                self.yield_curve_nominal.yield_curve_date + ' nominal';

        self.table = 'ssa-cohort'
        self.table_annuity = 'iam2012-basic'

        self.life_table_120 = LifeTable('death_120', 'male', 0)

        self.sex = data['sex']
        self.age = float(data['age'])
        self.le_set = float(data['le_set']) - self.age if data['le_set'] else None
        self.life_table = LifeTable(self.table, self.sex, self.age, le_set = self.le_set, date_str = self.date_str)
        self.life_table_annuity = LifeTable(self.table_annuity, self.sex, self.age, ae = 'aer2005_08-summary')

        self.sex2 = data['sex2']
        if self.sex2 == 'none':
            self.life_table2 = None
            self.life_table2_annuity = None
            self.min_age = self.age
        else:
            self.age2 = float(data['age2']);
            self.le_set2 = float(data['le_set2']) - self.age2 if data['le_set2'] else None
            self.life_table2 = LifeTable(self.table, self.sex2, self.age2, le_set = self.le_set2, date_str = self.date_str)
            self.life_table2_annuity = LifeTable(self.table_annuity, self.sex2, self.age2, ae = 'aer2005_08-summary')
            self.min_age = min(self.age, self.age2)

        self.db = data['db']
        if mode == 'aa':
            self.traditional = float(data['p_traditional_iras'])
            self.tax_rate = float(data['tax_rate_pct']) / 100
            self.npv_roth = float(data['p_roth_iras'])
            self.npv_taxable = float(data['p'])
            self.contribution = float(data['contribution'])
            self.contribution_growth = float(data['contribution_growth_pct']) / 100
            self.contribution_vol = float(data['contribution_vol_pct']) / 100
            self.equity_contribution_corr = float(data['equity_contribution_corr_pct']) / 100
            self.bonds_contribution_corr = float(data['bonds_contribution_corr_pct']) / 100
        else:
            self.traditional = 0
            self.tax_rate = 0
            self.npv_roth = 0
            self.npv_taxable = 0
            self.contribution = 0
            self.contribution_growth = 0
            self.contribution_vol = 0
            self.equity_contribution_corr = 0
            self.bonds_contribution_corr = 0
        self.retirement_age = float(data['retirement_age'])
        self.pre_retirement_years = max(0, self.retirement_age - self.age)
        self.payout_delay = self.pre_retirement_years * 12
        self.joint_payout_fraction = float(data['joint_income_pct']) / 100
        self.required_income = None if data['required_income'] == None else float(data['required_income'])
        self.desired_income = None if data['desired_income'] == None else float(data['desired_income'])
        self.use_lm_bonds = data['use_lm_bonds']
        self.bonds_vol_short = float(data['bonds_vol_pct']) / 100
        self.bonds_lm_bonds_corr_short = float(data['bonds_lm_bonds_corr_short_pct']) / 100
        self.risk_tolerance = float(data['risk_tolerance_pct']) / 100

        results['pre_retirement_years'] = '{:.1f}'.format(self.pre_retirement_years)

        self.period_certain = self.pre_retirement_years
            # For planning purposes when computing the npv of defined benefits
            # and contributions we need to assume we will reach retirement.

        self.frequency = 12 # Monthly. Makes accurate, doesn't run significantly slower.
        self.cpi_adjust = 'calendar'

        self.nv_contributions, self.ret_contributions = self.npv_contrib(self.contribution_growth)

        display_db, self.nv_db = self.value_table_db(self.life_table, self.life_table2)
        npv_results, npv_display = self.value_table(self.nv_db, self.npv_taxable)
        results['db'] = []
        for db in display_db:
            results['db'].append({'present': db})

        scenario = Scenario(self.yield_curve_zero, self.payout_delay, None, None, 0, self.life_table, life_table2 = self.life_table2, \
            joint_payout_fraction = self.joint_payout_fraction, joint_contingent = True, \
            period_certain = 0, frequency = self.frequency, cpi_adjust = self.cpi_adjust)
        self.retirement_le = scenario.price()

        scenario = Scenario(self.yield_curve_real, self.payout_delay, None, None, 0, self.life_table_annuity, life_table2 = self.life_table2_annuity, \
            joint_payout_fraction = self.joint_payout_fraction, joint_contingent = True, \
            period_certain = 0, frequency = self.frequency, cpi_adjust = self.cpi_adjust)
        self.discounted_retirement_le_annuity = scenario.price()

        scenario = Scenario(self.yield_curve_real, self.payout_delay, None, None, 0, self.life_table, life_table2 = self.life_table2, \
            joint_payout_fraction = self.joint_payout_fraction, joint_contingent = True, \
            period_certain = 0, frequency = self.frequency, cpi_adjust = self.cpi_adjust)
        self.discounted_retirement_le = scenario.price()
        self.lm_bonds_ret = scenario.annual_return
        self.lm_bonds_duration = scenario.duration

        self.real_vol = float(data['real_vol_10yr_pct']) / 100
        modified_duration = self.lm_bonds_duration / (1 + self.lm_bonds_ret)
        self.lm_bonds_vol_short = modified_duration / 10.0 * self.real_vol

        factor = norm.ppf(0.5 + float(data['confidence_pct']) / 100 / 2)
        factor = float(factor) # De-numpyfy.
        baseline = self.calc(mode, 'Baseline estimate', 0, data, npv_results, npv_display, None)
        low = self.calc(mode, 'Low returns estimate', - factor, data, npv_results, npv_display, baseline['annuitize_plan'])
        high = self.calc(mode, 'High returns estimate', factor, data, npv_results, npv_display, baseline['annuitize_plan'])
        results['calc'] = (baseline, low, high)

        if mode == 'number':
            self.npv_taxable = results['calc'][0]['taxable']
            npv_display = results['calc'][0]['npv_display'] # Use baseline scenario for common calculations display.

        results['present'] = npv_display

        #actual_display_db, actual_nv_db = self.value_table_db(self.life_table, self.life_table2)
        #_, actual_npv_display = self.value_table(actual_nv_db, self.npv_taxable)
        #for i, db in enumerate(actual_display_db):
        #    results['db'][i]['actual'] = db
        #results['actual'] = actual_npv_display

        return results

    def plot(self, mode, result, healthcheck):
        umask(0077)
        parent = STATIC_ROOT + 'results'
        prefix = 'healthcheck-' if healthcheck else 'aa-'
        dirname = mkdtemp(prefix=prefix, dir=parent)
        f = open(dirname + '/alloc.csv', 'w')
        f.write('class,allocation\n')
        f.write('stocks,%f\n' % result['w_fixed'][stocks_index])
        f.write('regular bonds,%f\n' % result['w_fixed'][bonds_index])
        f.write('LM bonds,%f\n' % result['w_fixed'][risk_free_index])
        f.write('defined benefits,%f\n' % result['w_fixed'][existing_annuities_index])
        f.write('new annuities,%f\n' % result['w_fixed'][new_annuities_index])
        if mode == 'aa':
            f.write('future contribs,%f\n' % result['w_fixed'][contrib_index])
        f.close()
        f = open(dirname + '/aa.csv', 'w')
        f.write('''asset class,allocation
stocks,%(aa_equity)f
bonds,%(aa_bonds)f
''' % result)
        f.close()
        cmd = ROOT + '/web/plot.R'
        prefix = dirname + '/'
        check_call((cmd, '--args', prefix))
        return dirname

    def alloc_init(self, data, mode):

        return AllocAaForm(data) if mode == 'aa' else AllocNumberForm(data)

    def alloc(self, request, mode, healthcheck):

        errors_present = False

        results = {}

        if request.method == 'POST':

            alloc_form = self.alloc_init(request.POST, mode)

            if alloc_form.is_valid():

                try:

                    data = alloc_form.cleaned_data
                    results = self.compute_results(data, mode)
                    dirname = self.plot(mode, results['calc'][0], healthcheck)
                    results['dirurl'] = dirname.replace(STATIC_ROOT, STATIC_URL)

                except LifeTable.UnableToAdjust:

                    errors = alloc_form._errors.setdefault('le_set2', ErrorList())  # Simplified in Django 1.7.
                    errors.append('Unable to adjust life table.')

                    errors_present = True

                except YieldCurve.NoData:

                    errors = alloc_form._errors.setdefault('date', ErrorList())  # Simplified in Django 1.7.
                    errors.append('No interest rate data available for the specified date.')

                    errors_present = True

                except self.IdenticalCovarError:

                    errors = alloc_form._errors.setdefault(NON_FIELD_ERRORS, ErrorList())  # Simplified in Django 1.7.
                    errors.append('Two or more rows of covariance matrix appear equal under scaling. This means asset allocation has no unique solution.')

                    errors_present = True

            else:

                errors_present = True

        else:

            alloc_form = self.alloc_init(self.default_alloc_params(), mode)

        return render(request, 'alloc.html', {
            'errors_present': errors_present,
            'mode': mode,
            'alloc_form': alloc_form,
            'results': results,
        })

def alloc(request, mode, healthcheck=False):
    return Alloc().alloc(request, mode, healthcheck)
