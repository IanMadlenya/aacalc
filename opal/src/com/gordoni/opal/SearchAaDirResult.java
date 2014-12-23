/*
 * AACalc - Asset Allocation Calculator
 * Copyright (C) 2009, 2011-2015 Gordon Irlam
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

public class SearchAaDirResult
{
        public double[] aa;
        public double contrib;
        public SimulateResult results;
        public boolean both_dir;
        public double biggest_step;

        public SearchAaDirResult(double[] aa, double contrib, SimulateResult results, boolean both_dir, double biggest_step)
        {
                this.aa = aa;
                this.contrib = contrib;
                this.results = results;
                this.both_dir = both_dir;
                this.biggest_step = biggest_step;
        }
}
