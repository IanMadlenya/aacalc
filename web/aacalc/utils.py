# AACalc - Asset Allocation Calculator
# Copyright (C) 2009, 2011-2015 Gordon Irlam
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

asset_classes = (
    ('stocks',         'class_stocks',    'stocks',         1872, 2013),
    ('bonds',          'class_bonds',     'bonds',          1872, 2013),
    ('eafe',           'class_eafe',      'international',  1970, 2013),
    ('bl',             'class_ff_bl',     'large growth',   1927, 2013),
    ('bm',             'class_ff_bm',     'large neutral',  1927, 2013),
    ('bh',             'class_ff_bh',     'large value',    1927, 2013),
    ('sl',             'class_ff_sl',     'small growth',   1927, 2013),
    ('sm',             'class_ff_sm',     'small neutral',  1927, 2013),
    ('sh',             'class_ff_sh',     'small value',    1927, 2013),
    ('equity_reits',   'class_reits_e',   'equity reits',   1972, 2013),
    ('mortgage_reits', 'class_reits_m',   'mortgage reits', 1972, 2013),
    ('baa',            'class_baa',       'baa long corp',  1920, 2013),
    ('aaa',            'class_aaa',       'aaa long corp',  1920, 2013),
    ('gs10',           'class_t10yr',     't-note 10yr',    1872, 2013),
    ('gs1',            'class_t1yr',      't-bill 1yr',     1954, 2013),
    ('cash',           'class_t1mo',      't-bill 1mo',     1927, 2013),
    ('tips',           'class_tips10yr',  'tips 10yr',      1972, 2013),
    ('gold',           'class_gold',      'gold',           1872, 2013),
    ('risk_free',      'class_risk_free', 'risk free',      1872, 2013),
)

def all_asset_classes():
    return tuple(asset_class for (_, asset_class, _, _, _) in asset_classes)

def asset_class_symbols(s):
    return tuple(symbol for (symbol, asset_class, _, _, _) in asset_classes if s[asset_class])

def asset_class_names(s):
    return tuple(name for (_, asset_class, name, _, _) in asset_classes if s[asset_class])

def too_early_for_asset_classes(s, year):
    return {asset_class: s[asset_class] and year < start for (_, asset_class, _, start, _) in asset_classes}

def too_late_for_asset_classes(s, year):
    return {asset_class: s[asset_class] and year > end for (_, asset_class, _, _, end) in asset_classes}