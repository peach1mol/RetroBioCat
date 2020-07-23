import pandas as pd
import numpy as np
from rdkit import DataStructs
from rdkit.Chem import AllChem
import time
from retrobiocat_web.retro.enzyme_identification.load import make_fingerprints
from retrobiocat_web.retro.enzyme_identification import query_mongodb



class SpecificityColumns():

    def __init__(self):
        self.subOneSmiCol = 'Substrate 1 SMILES'
        self.subOneFingCol = 'Substrate 1 Fingerprint'
        self.subTwoSmiCol = 'Substrate 2 SMILES'
        self.subTwoFingCol = 'Substrate 2 Fingerprint'
        self.prodOneSmiCol = 'Product 1 SMILES'
        self.prodOneFingCol = 'Product 1 Fingerprint'
        self.subSimCol = 'Substrate Similarity'
        self.prodSimCol = 'Product 1 Similarity'
        self.reactionCol = 'Reaction'
        self.enzCol = 'Enzyme type'
        self.simScoreCol = 'Similarity'
        self.binaryCol = 'Binary'
        self.auto_generated = 'Auto Generated'

class SubstrateSpecificityScorer():

    def __init__(self,
                 score_substrates=False,
                 mode=make_fingerprints.default_fp_mode,
                 print_log=False, log_times=False):

        self.mode = mode

        self.fingerprintDf = make_fingerprints.load_fp_df_from_mongo(self.mode)

        fingerprint_settings = make_fingerprints.fingerprint_options[self.mode]
        self.fp_gen = make_fingerprints.make_fp_generator(fingerprint_settings[0],
                                                          fingerprint_settings[1])

        self.cols = SpecificityColumns()

        self.score_substrates = score_substrates
        self.print_log = print_log
        self.log_times = log_times

    def scoreReaction(self, reaction, enzyme, p1, s1, s2, sim_cutoff=0.7, onlyActive=True):

        spec_df = query_mongodb.query_specificity_data([reaction], [enzyme])
        if len(spec_df.index) != 0:
            spec_df_f = self.get_fingerprints(spec_df)
            spec_df_f = self.drop_fingerprint_nan(spec_df_f, p1, s1, s2)

            if len(spec_df_f.index) != 0:
                sim_df = self.calculate_similarity(spec_df_f, p1, s1, s2)
                top_df = self.get_top_similarity_df(sim_df, sim_cutoff, onlyActive)
                bestEnzDf = self.get_best_enzymes(top_df, 1, 1)

                if len(bestEnzDf) != 0:
                    score = bestEnzDf.iloc[0][self.cols.simScoreCol]
                    info = self.info_from_top_df(bestEnzDf)

                    if bestEnzDf.iloc[0][self.cols.binaryCol] == 0:
                        score = score * -1

                    return score, info

        return 0, False

    def querySpecificityDf(self, productSmi, listReactionNames, listEnzymes,
                           dataLevel='All', numEnzymes=5, numHits=2, simCutoff=0.65,
                           include_auto_generated=True):



        spec_df = query_mongodb.query_specificity_data(listReactionNames, listEnzymes)
        self._log(f'Queried mongodb, retrieved {len(spec_df.index)} entries')

        spec_df = self.filter_df_by_data_level(spec_df, dataLevel)

        if include_auto_generated == False:
            self._log('Filtering out auto generated data..')
            spec_df = spec_df[spec_df[self.cols.auto_generated] != 1]


        if productSmi != '':
            self._log('Product entered, getting similar products..')
            spec_df_f = self.get_fingerprints(spec_df)
            spec_df_f = self.drop_fingerprint_nan(spec_df_f, productSmi, None, None)
            self._log(f"Fingerprint entries = {len(spec_df_f.index)}")

            if len(spec_df_f.index) != 0:
                sim_df = self.calculate_similarity(spec_df_f, productSmi, None, None)
                top_df = self.get_top_similarity_df(sim_df, simCutoff, False)
                return self.get_best_enzymes(top_df, numEnzymes, numHits)
            else:
                self._log("No similar fingerprints found")
                return None

        else:
            self._log('No product, getting best enzymes..')
            return self.get_best_enzymes(spec_df, numEnzymes, False)

    def get_fingerprints(self, spec_df):
        how = 'left'

        spec_df = spec_df.merge(self.fingerprintDf, how=how, left_on=self.cols.prodOneSmiCol, right_on='smiles')
        spec_df = spec_df.rename(columns={"fp": self.cols.prodOneFingCol})
        spec_df = spec_df.drop(columns=['smiles'])

        if self.score_substrates==True:
            spec_df = spec_df.merge(self.fingerprintDf, how=how, left_on=self.cols.subOneSmiCol, right_on='smiles')
            spec_df = spec_df.rename(columns={"fp": self.cols.subOneFingCol})
            spec_df = spec_df.drop(columns=['smiles'])

            spec_df = spec_df.merge(self.fingerprintDf, how=how, left_on=self.cols.subTwoSmiCol, right_on='smiles')
            spec_df = spec_df.rename(columns={"fp": self.cols.subTwoFingCol})
            spec_df = spec_df.drop(columns=['smiles'])

        return spec_df

    def drop_fingerprint_nan(self, df, p, s1, s2):
        if p != None and p != '':
            df = df.dropna(subset=[self.cols.prodOneFingCol])

        if self.score_substrates==True:
            if s1 != None and s1 != '':
                df = df.dropna(subset=[self.cols.subOneFingCol])
            if s2 != None and s2 != '':
                df = df.dropna(subset=[self.cols.subTwoFingCol])
        return df

    def calculate_similarity(self, spec_df_f, productSmi, substrateOneSmi, substrateTwoSmi):
        productFp = self._get_fingerprint(productSmi)
        substrateOneFp = self._get_fingerprint(substrateOneSmi)
        substrateTwoFp = self._get_fingerprint(substrateTwoSmi)

        if productFp != None:
            spec_df_f[self.cols.prodSimCol] = DataStructs.BulkTanimotoSimilarity(productFp, list(spec_df_f[self.cols.prodOneFingCol]))

        if self.score_substrates==True:
            if substrateOneFp != None:
                if substrateTwoFp == None:
                    spec_df_f[self.cols.subSimCol] = DataStructs.BulkTanimotoSimilarity(substrateOneFp, list(spec_df_f[self.cols.subOneFingCol]))
                else:
                    spec_df_f['s1_s1'] = DataStructs.BulkTanimotoSimilarity(substrateOneFp, list(spec_df_f[self.cols.subOneFingCol]))
                    spec_df_f['s1_s2'] = DataStructs.BulkTanimotoSimilarity(substrateOneFp,
                                                                            list(spec_df_f[self.cols.subTwoFingCol]))
                    spec_df_f['s2_s1'] = DataStructs.BulkTanimotoSimilarity(substrateTwoFp,
                                                                            list(spec_df_f[self.cols.subOneFingCol]))
                    spec_df_f['s2_s2'] = DataStructs.BulkTanimotoSimilarity(substrateTwoFp,
                                                                            list(spec_df_f[self.cols.subTwoFingCol]))

                    spec_df_f['1_2'] = spec_df_f['s1_s1'] + spec_df_f['s2_s2']
                    spec_df_f['2_1'] = spec_df_f['s1_s2'] + spec_df_f['s2_s1']
                    spec_df_f[self.cols.subSimCol] = spec_df_f[['1_2', '2_1']].max(axis=1)

        if self.cols.prodSimCol in spec_df_f.columns:
            if self.cols.subSimCol in spec_df_f.columns:
                spec_df_f[self.cols.simScoreCol] = (spec_df_f[self.cols.prodSimCol] + spec_df_f[self.cols.subSimCol]) / 2
            else:
                spec_df_f[self.cols.simScoreCol] = spec_df_f[self.cols.prodSimCol]

        elif self.cols.subSimCol in spec_df_f.columns:
            spec_df_f[self.cols.simScoreCol] = spec_df_f[self.cols.subSimCol]

        else:
            spec_df_f[self.cols.simScoreCol] = 0

        spec_df_f = spec_df_f.sort_values((self.cols.simScoreCol), ascending=False)
        return spec_df_f

    def get_top_similarity_df(self, simDf, cutoff, onlyActive):

        topDf = simDf[simDf[self.cols.simScoreCol] >= cutoff]

        if onlyActive == True:
            topDf = topDf[topDf[self.cols.binaryCol] == 1]

        return topDf

    def get_best_enzymes(self, topDf, numEnzymes, maxHits):

        top_enzymes = pd.DataFrame()

        listSmi = []
        numHits = 0
        for index, row in topDf.iterrows():
            rowSmi = str([row[self.cols.subOneSmiCol], row[self.cols.subTwoSmiCol], row[self.cols.prodOneSmiCol]])
            if (rowSmi not in listSmi) and (numHits<maxHits or maxHits==False):
                listSmi.append(rowSmi)
                numHits += 1
                candidates = topDf[(topDf[self.cols.subOneSmiCol]).isin([row[self.cols.subOneSmiCol]]) &
                                   (topDf[self.cols.subTwoSmiCol].isin([row[self.cols.subTwoSmiCol]])) &
                                   (topDf[self.cols.prodOneSmiCol].isin([row[self.cols.prodOneSmiCol]]))]

                column_to_sort_on = self._find_activity_to_sort_on(candidates)
                candidates = candidates.sort_values(column_to_sort_on, ascending=False)
                candidates = candidates.iloc[0:numEnzymes]
                top_enzymes = top_enzymes.append(candidates)

        return top_enzymes

    def info_from_top_df(self, top_df):
        info = {'Score' : top_df.iloc[0][self.cols.simScoreCol]}
        for index, row in top_df.iterrows():
            smiles_dict = {}
            smiles = row['Product 1 SMILES']
            smiles_dict['Similarity'] = round(row['Similarity'],2)
            smiles_dict['Active (1 or 0)'] = row['Binary']
            smiles_dict['Enzyme name'] = row['Enzyme name']
            smiles_dict['Data source'] = row['Data source']

            if type(row['Categorical']) == str:
                smiles_dict['Activity Level'] = row['Categorical']
            if np.isnan(row['Conversion (%)']) == False:
                smiles_dict['Conversion (%)'] = row['Conversion (%)']
            if np.isnan(row['Specific activity (U/mg)']) == False:
                smiles_dict['Specific activity (U/mg)'] = round(row['Specific activity (U/mg)'],2)

            info[smiles] = smiles_dict

        return info

    def filter_df_by_data_level(self, df, data_level):
        if data_level != 'All':
            if data_level == 'Categorical':
                df = df[df['Categorical'].notnull()]
            elif data_level == 'Quantitative':
                df1 = df[df['Specific activity (U/mg)'].notnull()]
                df2 = df[df['Conversion (%)'].notnull()]
                df = pd.concat([df1, df2])
            elif data_level == 'Specific Activity':
                df = df[df['Specific activity (U/mg)'].notnull()]
            elif data_level == 'Conversion':
                df = df[df['Conversion (%)'].notnull()]

        self._log(f'Filtered by data level {data_level}, {len(df.index)} entries returned')
        return df

    def _get_fingerprint(self, smi):
        if smi is None:
            return None
        try:
            mol = AllChem.MolFromSmiles(smi)
            #fp = FingerprintMols.FingerprintMol(mol)
        except:
            return None

        fp = self.fp_gen.GetFingerprint(mol)

        return fp

    def _find_activity_to_sort_on(self, df):
        specific = True
        conversion = True
        categorical = True
        binary = True

        for index, row in df.iterrows():
            if np.isnan(row['Specific activity (U/mg)']) == True:
                specific = False
            if np.isnan(row['Conversion (%)']) == True:
                conversion = False
            if row['Categorical'] != type(str):
                categorical = False
            # if np.isnan(row['Binary Activity (True or False)']) == True:
            # binary = False

        if specific == True:
            return 'Specific activity (U/mg)'
        elif conversion == True:
            return 'Conversion (%)'
        elif categorical == True:
            return 'Categorical'
        elif binary == True:
            return 'Binary'
        else:
            print('Error no activity category is suitable')
            return None

    def _log_time(self, msg):
        if self.log_times==True:
            print(msg)

    def _log(self, msg):
        if self.print_log==True:
            print(msg)




if __name__ == '__main__':
    from retrobiocat_web.mongo.default_connection import make_default_connection
    make_default_connection()

    t0 = time.time()
    scorer = SubstrateSpecificityScorer(log_times=True)
    t1 = time.time()
    print(f"Time to load = {round(t1-t0,3)}")
    reactionName = 'All'
    enzyme = 'CAR'
    product = 'CCc1ccc(C=O)cc1'

    score, info = scorer.scoreReaction(reactionName, enzyme, product, None, None,
                                       sim_cutoff=0.5, onlyActive=True)
    t2 = time.time()
    print(f"Time to score = {round(t2 - t1, 3)}")
    print(score)
    print(info)

    query_result = scorer.querySpecificityDf(product, [''], [enzyme],
                                             dataLevel='All', numEnzymes=1, numHits=5, simCutoff=0.4,
                                             include_auto_generated=True)


    t3 = time.time()
    print(query_result.iloc[0])
    print(f"Time to query = {round(t3 - t2, 3)}")
