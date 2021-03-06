/*
 * AACalc - Asset Allocation Calculator
 * Copyright (C) 2009, 2011-2017 Gordon Irlam
 *
 * This program is free software: you can redistribute it and/or modify
 * it under the terms of the GNU Affero General Public License as published by
 * the Free Software Foundation, either version 3 of the License, or
 * (at your option) any later version.
 *
 * This program is distributed in the hope that it will be useful,
 * but WITHOUT ANY WARRANTY; without even the implied warranty of
 * MERCHANTABILITY or FITNESS FOR A PARTICULAR PURPOSE.  See the
 * GNU Affero General Public License for more details.
 *
 * You should have received a copy of the GNU Affero General Public License
 * along with this program.  If not, see <http://www.gnu.org/licenses/>.
 */

package com.gordoni.opal;

public class UtilityPower extends Utility
{
        private Config config;
        private double public_assistance;
        private double public_assistance_phaseout_rate;
        private double offset;
        private double eta;
        private double scale;
        private double zero = 0;

        private boolean cache = false;
        private double[] utility_cache = null;  // Lookup is slow so we use a cache. Cache effective utility since it is smooth.

        public double utility(double c)
        {
                if (c < 0)
                {
                        System.out.println("utility(" + c + "): negative consumption");
                        assert(false);
                }
                if (c * public_assistance_phaseout_rate < public_assistance)
                        c = public_assistance + c * (1 - public_assistance_phaseout_rate);
                if (eta == 1)
                        return scale * Math.log((c - offset)) - zero;
                else
                        return scale * Math.pow((c - offset), 1 - eta) / (1 - eta) - zero;
        }

        public double inverse_utility(double u)
        {
                double c;
                if (scale == 0)
                {
                        assert(u == - zero);
                        c = 0;
                }
                else if (eta == 1)
                        c = offset + Math.exp((zero + u) / scale);
                else
                {
                        if ((eta > 1) && (zero + u >= 0))
                                return Double.POSITIVE_INFINITY; // Extrapolation may overshoot.
                        c = offset + Math.pow((zero + u) * (1 - eta) / scale, 1 / (1 - eta));
                }

                if (c * public_assistance_phaseout_rate < public_assistance)
                        return (c - public_assistance) / (1 - public_assistance_phaseout_rate);
                else
                        return c;
        }

        public double slope(double c)
        {
                assert(c >= 0);
                boolean assist = c * public_assistance_phaseout_rate < public_assistance;
                if (assist)
                        c = public_assistance + c * (1 - public_assistance_phaseout_rate);
                double slope = scale * Math.pow((c - offset), - eta);
                if (assist)
                        return (1 - public_assistance_phaseout_rate) * slope;
                else
                        return slope;
        }

        public double inverse_slope(double s)
        {
                // Bug: need to adjust s for public assistance; but method only used for testing so OK.
                double c;
                if (scale == 0)
                {
                        assert(s == 0);
                        c = 0;
                }
                else
                        c = offset + Math.pow(s / scale, - 1 / eta);
                if (c * public_assistance_phaseout_rate < public_assistance)
                        return (c - public_assistance) / (1 - public_assistance_phaseout_rate);
                else
                        return c;
        }

        public double slope2(double c)
        {
                assert(c >= 0);
                boolean assist = c * public_assistance_phaseout_rate < public_assistance;
                if (assist)
                        c = public_assistance + c * (1 - public_assistance_phaseout_rate);
                double slope2 = - scale * eta * Math.pow((c - offset), - eta - 1);
                if (assist)
                        return (1 - public_assistance_phaseout_rate) * (1 - public_assistance_phaseout_rate) * slope2;
                else
                        return slope2;
        }

        public UtilityPower(Config config, Double force_eta, double c_shift, double c, double u, Double ce, double ce_ratio, double c1, double s1, double c2, double s2, double public_assistance, double public_assistance_phaseout_rate, Double force_scale)
        {
                double c1_adjust = c1;
                double s1_adjust = s1;
                if (c1 * public_assistance_phaseout_rate < public_assistance)
                {
                        c1_adjust = public_assistance + c1 * (1 - public_assistance_phaseout_rate);
                }
                double c2_adjust = c2;
                double s2_adjust = s2;
                if (c2 * public_assistance_phaseout_rate < public_assistance)
                {
                        c2_adjust = public_assistance + c2 * (1 - public_assistance_phaseout_rate);
                }
                this.config = config;
                this.public_assistance = public_assistance;
                this.public_assistance_phaseout_rate = public_assistance_phaseout_rate;
                this.offset = c_shift;
                if (force_eta != null)
                        this.eta = force_eta;
                else if (ce != null)
                {
                        double low = 0;
                        double high = 100;
                        double mid;
                        while (true)
                        {
                                mid = (low + high) / 2;
                                if ((mid == low) || (mid == high))
                                        break;
                                double res = (mid == 1 ? Math.sqrt(ce_ratio) : Math.pow((1 + Math.pow(ce_ratio, 1 - mid)) / 2, 1 / (1 - mid)));
                                if (res < ce)
                                        high = mid;
                                else
                                        low = mid;
                        }
                        this.eta = mid;
                }
                else
                {
                        assert(c1_adjust > offset); // public_assistance must be positive unless force_eta.
                        assert(c2_adjust > offset);
                        if (s1_adjust == s2_adjust)
                        {
                                this.eta = 0;
                        }
                        else
                                this.eta = Math.log(s1_adjust / s2_adjust) / Math.log((c2_adjust - offset) / (c1_adjust - offset));
                }
                if (force_scale == null)
                        this.scale = s2_adjust * Math.pow(c2_adjust - offset, eta);
                else
                        this.scale = force_scale;
                this.zero = utility(c) - u;
                //assert(utility(c) == u);
                //assert(Math.abs(slope(c1) - s1) < 1e-6);
                //assert(Math.abs(slope(c2) - s2) < 1e-6);

                // final boolean enable_cache = false;
                // Cache is disabled for now. A bug once meant consumption lookups are all very close. The cache makes them linear.
                // This makes the nearby consume utility constant for different contrib values as lower target_consume_utility values have higher solvencies.
                // This makes aa_search_dir walk much further than it should.  Whether other parts of the system generate close lookups is unclear.
                // Play it safe, and employ a local cache inside simulate().
                // if (enable_cache && config.utility_steps > 0)
                // {
                //         utility_cache = new double[config.utility_steps + 1];
                //      for (int i = 0; i <= config.utility_steps; i++)
                //      {
                //              utility_cache[i] = effective_utility(range * i / config.utility_steps);
                //      }
                //      cache = true;
                // }

                set_constants();
        }
}
