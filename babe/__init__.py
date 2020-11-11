from io import BytesIO
from functools import lru_cache, cached_property
from collections import defaultdict, Counter

import pandas as pd
from graze import Graze
from py2store import FilesOfZip, filt_iter, wrap_kvs


#
# us_names_src_url = "http://www.ssa.gov/oact/babynames/state/namesbystate.zip"
#
# names_by_us_states = filt_iter(FilesOfZip(BytesIO(g[us_names_src_url])),
#                                filt=lambda x: x.endswith('.TXT'))
# names_by_us_states = wrap_kvs(
#     names_by_us_states,
#     obj_of_data=lambda data: pd.read_csv(BytesIO(data),
#                                          header=None,
#                                          names=['state', 'gender', 'year', 'name', 'popularity']),
#     key_of_id=lambda _id: _id[:-4],
#     id_of_key=lambda _id: _id + '.TXT'
# )
#
# names_by_us_states = pd.concat(names_by_us_states.values())
# names_by_us_states['name_g'] = names_by_us_states['name'] + '_' + names_by_us_states['gender']
#
# names_all_us_states = (names_by_us_states
#                        .groupby(['name_g', 'year'])
#                        .sum())
#
# names_by_us_states = names_by_us_states.set_index(['state', 'name_g', 'year'])
#
#
# @lru_cache(1)
# def __gender_of_name():
#     return dict(names_by_us_states.reset_index(level='name')[['name_g', 'gender']].values)
#
#
# def gender_of_name(name):
#     """Get gender of name"""
#     return __gender_of_name().get(name, None)


class UsNames:
    us_names_src_url = "http://www.ssa.gov/oact/babynames/state/namesbystate.zip"

    @cached_property
    def _names_by_us_states_store(self):
        g = Graze()
        names_by_us_states = filt_iter(FilesOfZip(BytesIO(g[self.us_names_src_url])),
                                       filt=lambda x: x.endswith('.TXT'))
        return wrap_kvs(
            names_by_us_states,
            obj_of_data=lambda data: pd.read_csv(BytesIO(data),
                                                 header=None,
                                                 names=['state', 'gender', 'year', 'name', 'popularity']),
            key_of_id=lambda _id: _id[:-4],
            id_of_key=lambda _id: _id + '.TXT'
        )

    @cached_property
    def data(self):
        df = pd.concat(self._names_by_us_states_store.values())
        df['name_g'] = df['name'] + '_' + df['gender']
        return df
        # return df.set_index(['state', 'name_g', 'year'])

    @cached_property
    def by_state(self):
        return self.data.set_index(['state', 'name_g', 'year'])['popularity']

    @cached_property
    def national(self):
        df = (self.data
              .groupby(['name_g', 'year'])
              .sum()
              )

        return df['popularity']

    @cached_property
    def all_time_national(self):
        return self.national.reset_index()[['name_g', 'popularity']].groupby('name_g').sum()['popularity']

    @cached_property
    def names(self):
        return set(self.data['name'].values)

    @cached_property
    def name_gs(self):
        return set(self.data['name_g'].values)

    @cached_property
    def name_gs_of_name(self):
        d = defaultdict(set)
        for name_g in self.name_gs:
            d[name_g[:-2]].add(name_g)

        return dict(d)

    @cached_property
    def gender_count_of_name(self):
        d = defaultdict(Counter)
        for name_g, popularity in self.all_time_national.items():
            name, gender = name_g[:-2], name_g[-1]
            d[name].update({gender: popularity})

        return {k: dict(v) for k, v in d.items()}

    @cached_property
    def genders_of_name(self):
        return {k: set(v) for k, v in self.gender_count_of_name.items()}

    @cached_property
    def femininity_of_name(self):
        return pd.Series({name_g: v.get('F', 0) / (v.get('F', 0) + v.get('M', 0))
                          for name_g, v in self.gender_count_of_name.items()}).sort_values()

    @cached_property
    def masculinity_of_name(self):
        return pd.Series({name_g: v.get('M', 0) / (v.get('F', 0) + v.get('M', 0))
                          for name_g, v in self.gender_count_of_name.items()}).sort_values()

    @cached_property
    def ambiguity_of_name(self):
        return 2 * (pd.concat([self.femininity_of_name, self.masculinity_of_name], axis=1)
                    .min(axis=1)
                    .sort_values(ascending=False))

    @cached_property
    def year_range(self):
        years = set(self.data['year'])
        return min(years), max(years)

    def name_kind(self, name):
        """Returns a kind for the name: 'name' or 'name_g'"""
        if name[-2:] in {'_M', '_F'}:
            return 'name_g'
        else:
            return 'name'

    def name_is_ambiguous(self, name):
        """Returns True iff the name can be both genders"""
        return (
                self.name_kind(name) == 'name'  # is not a name_g
                and len(self.name_gs_of_name[name]) > 1  # and can have several genders
        )

    @cached_property
    def ambiguous_names(self):
        return set(filter(self.name_is_ambiguous, self.names))

    def resolve_name_g(self, name):
        """Returns the name_g corresponding to name (or raises an Assertion error if name can't be resolved)"""
        name_kind = self.name_kind(name)
        if name_kind == 'name':
            assert name in self.names, f"I don't have that name in my data: {name}"
            name_gs_for_name = self.name_gs_of_name[name]
            assert len(name_gs_for_name) == 1, f"The {name} can be used for both genders. Specify {name}_F or {name}_M"
            name_g, *_ = name_gs_for_name
        else:
            assert name in self.name_gs, f"I don't have that name in my data: {name}"
            name_g = name

        return name_g

    def plot_popularity(self, name, state=None, style='-o', figsize=(17, 4), grid=True, xlim=(1900, 2020), **kwargs):
        plot_kwargs = dict(figsize=figsize, style=style, grid=grid, xlim=xlim, **kwargs)
        if isinstance(name, str):
            name = [name]
        name_gs = list(map(self.resolve_name_g, name))

        if state is None:
            t = self.national.loc[name_gs].reset_index().pivot(index='year', columns='name_g', values='popularity')
            title = f"Number of babies named {', '.join(name_gs)} (nationally)"
        else:
            if isinstance(state, str):
                state = [state]
            else:
                state = list(state)  # to make sure it's a list, so it's interpreted as a multi-select
            t = self.by_state.loc[state, name_gs].reset_index()
            if len(name) == 1:
                t = t.pivot(index='year', columns='state', values='popularity')
            elif len(state) == 1:
                t = t.pivot(index='year', columns='name_d', values='popularity')
            else:
                t = t.pivot(index='year', columns=['name_g', 'state'], values='popularity')
            title = f"Number of babies named {', '.join(name_gs)} in {', '.join(state)}"

        return t.plot(title=title, **plot_kwargs)
