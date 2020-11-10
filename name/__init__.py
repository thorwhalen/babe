from io import BytesIO
import pandas as pd
from graze import Graze
from py2store import FilesOfZip, filt_iter, wrap_kvs

g = Graze()

us_names_src_url = "http://www.ssa.gov/oact/babynames/state/namesbystate.zip"

names_by_us_states = filt_iter(FilesOfZip(BytesIO(g[us_names_src_url])),
                               filt=lambda x: x.endswith('.TXT'))
names_by_us_states = wrap_kvs(
    names_by_us_states,
    obj_of_data=lambda data: pd.read_csv(BytesIO(data),
                                         header=None,
                                         names=['state', 'gender', 'year', 'name', 'popularity']),
    key_of_id=lambda _id: _id[:-4],
    id_of_key=lambda _id: _id + '.TXT'
)

names_by_us_states = pd.concat(names_by_us_states.values())

names_all_us_states = (names_by_us_states
                       .groupby(['name', 'year'])
                       .sum())

names_by_us_states = names_by_us_states.set_index(['state', 'name', 'year'])