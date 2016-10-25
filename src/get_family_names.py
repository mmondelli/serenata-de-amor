# coding: utf-8

import os
import re
import datetime
import requests
import numpy as np
import pandas as pd
from bs4 import BeautifulSoup

DATE = datetime.date.today().strftime('%Y-%m-%d')
DATA_DIR = 'data'
PROCESSED_DATA_PATH = os.path.join(DATA_DIR, '{}-congressperson_relatives.xz').format(DATE)
RAW_DATA_PATH = os.path.join(DATA_DIR, '{}-congressperson_relatives_raw.xz').format(DATE)

write_csv_params = {
    'compression': 'xz',
    'encoding': 'utf-8',
    'index': False}


def format_string(s):
    return s.strip().replace(':', '')


def extract_contents_from_div(div):
    return list(map(format_string,
                    filter(lambda x: '\n' not in x,
                           div[0].strings)))


def convert_to_dict(contents):
    return dict(zip(contents[1:-2:2],
                    contents[2:-1:2]))


def is_single_word(s):
    return (' ' not in s)


def fix_when_theres_a_single_surname_after_the_split(names):
    pairs = [(i, name) for i, name
             in enumerate(names) if is_single_word(name)]
    while pairs:
        i, name = pairs.pop(0)
        if i == 0:
            continue
        names_to_join = names[i-1:i+1]
        name = ' e '.join(names_to_join)
        for n in names_to_join:
            names.remove(n)
        names.append(name)
        pairs = [(i, name) for i, name
                 in enumerate(names) if is_single_word(name)]
    return names


def split_names(s):
    names = s.split(' e ')
    names = fix_when_theres_a_single_surname_after_the_split(names)
    return names


def create_one_row_per_parent(df):
    result = []
    dict_df = df.to_dict(orient='records')[0]
    for name in dict_df['parents_list']:
        result.append({'id': dict_df['id'],
                       'relative_name': name,
                       'relationship': 'son_of'})
    return pd.DataFrame(data=result)


def get_all_congress_people_ids():
    print('Fetching all congresspeople ids', end='\r')
    ids_series = [read_csv(name)['congressperson_id']
                  for name in ['current-year', 'last-year', 'previous-years']]
    return list(pd.concat(ids_series).unique())


def find_latest_date():
    date_regex = re.compile('\d{4}-\d{2}-\d{2}')

    matches = (date_regex.findall(f) for f in os.listdir(DATA_DIR))
    dates = (l[0] for l in matches if l)
    return max(dates)


def read_csv(name):
    date = find_latest_date()
    return pd.read_csv('data/{}-{}.xz'.format(date, name),
                       parse_dates=[16],
                       dtype={'document_id': np.str,
                              'congressperson_id': np.str,
                              'congressperson_document': np.str,
                              'term_id': np.str,
                              'cnpj_cpf': np.str,
                              'reimbursement_number': np.str})


def write_formatted_data(df):
    people_with_two_or_less_parents = (
        df
        [df.parents_list.apply(len) <= 2]
        [['id', 'parents_list']])

    final = (
        people_with_two_or_less_parents
        .groupby('id')
        .apply(create_one_row_per_parent)
        .reset_index(drop=True))

    final.rename(inplace=True, columns={'id': 'congressperson_id'})
    final.to_csv(PROCESSED_DATA_PATH, **write_csv_params)


def write_raw_data(df):
    people_with_more_than_two_parents = (
        df
        [df.parents_list.apply(len) > 2]
        [['id', 'Filiação']])

    people_with_more_than_two_parents.rename(inplace=True, columns={
        'id': 'congressperson_id',
        'Filiação': 'parents'})

    if len(people_with_more_than_two_parents):
        people_with_more_than_two_parents.to_csv(RAW_DATA_PATH, **write_csv_params)


def get_congresspeople_parents_names():
    url = 'http://www2.camara.leg.br/deputados/pesquisa/layouts_deputados_' \
          'biografia?pk={}'

    ids = get_all_congress_people_ids()

    dicts = []
    total = len(ids)
    for i, id in enumerate(ids):
        id = str(id).replace('\n', '').strip()
        try:
            data = requests.get(url.format(id)).content.decode('utf8')
            soup = BeautifulSoup(str(data), 'html.parser')
            bio_details = soup.findAll('div', {'class': 'bioDetalhes'})
            contents_bio_details = extract_contents_from_div(bio_details)
            dict_bio_details = convert_to_dict(contents_bio_details)
            dict_bio_details['id'] = id
            dicts.append(dict_bio_details)
        except IndexError:
            print('Could not parse data')
        print('Processed {} out of {} ({:.2f}%)'.format(i, total, i / total * 100), end='\r')

    df = pd.DataFrame(data=dicts)
    df = df[df['Filiação'].notnull()]
    df = df[~(df['Filiação'].str.contains('Escolaridade'))]
    df['parents_list'] = df['Filiação'].apply(split_names)

    write_formatted_data(df)
    write_raw_data(df)


if __name__ == '__main__':
    get_congresspeople_parents_names()
