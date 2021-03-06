import requests
import pandas as pd
import numpy as np
import io
from nltk.corpus import stopwords
stop = stopwords.words('english')

def remove_stopwords(df, column: str):
   df[column +"_without_stopwords"] = df[column].apply(lambda x: ' '.join([word for word in x.split() if word not in stop]))
   return df
# url = "https://raw.githubusercontent.com/brmson/dataset-sts/master/data/sts/sick2014/SICK_train.txt"

# text = requests.get(url).text

# data = pd.read_csv(io.StringIO(text), sep="\t")
data = pd.read_csv('plagiarism.csv', encoding= 'unicode_escape')
# print(data.head())

#data = remove_stopwords(data, 'Sentences')

#sentences = data['Sentences_without_stopwords'].tolist()
sentences = data['Sentences'].tolist()
# print(sentences[:3])

#We have our data, now to shingle and one-hot encode it.
def build_shingles(sentence: str, k: int):
    shingles = []
    for i in range(len(sentence) - k):
        shingles.append(sentence[i:i+k])
    return set(shingles)

def build_vocab(shingle_sets: list):
    # convert list of shingle sets into single set
    full_set = {item for set_ in shingle_sets for item in set_}
    vocab = {}
    for i, shingle in enumerate(list(full_set)):
        vocab[shingle] = i
    return vocab

def one_hot(shingles: set, vocab: dict):
    vec = np.zeros(len(vocab))
    for shingle in shingles:
        idx = vocab[shingle]
        vec[idx] = 1
    return vec

k = 6  # shingle size

# build shingles
shingles = []
for sentence in sentences:
    shingles.append(build_shingles(sentence, k))

# build vocab
vocab = build_vocab(shingles)

# one-hot encode our shingles
shingles_1hot = []
for shingle_set in shingles:
    shingles_1hot.append(one_hot(shingle_set, vocab))
# stack into single numpy array
shingles_1hot = np.stack(shingles_1hot)
print(shingles_1hot.shape)

print(shingles_1hot[0].shape)

# print(sum(shingles_1hot[0])) # confirm we have 1s

# MinHash
# Now we move onto minhashing, first we need to create functions for building a range of minhash vectors, and another to process our sparse vectors through this minhash array - to produce our signatures.

def minhash_arr(vocab: dict, resolution: int):
    length = len(vocab.keys())
    arr = np.zeros((resolution, length))
    for i in range(resolution):
        permutation = np.random.permutation(len(vocab)) + 1
        arr[i, :] = permutation.copy()
    return arr.astype(int)

def get_signature(minhash, vector):
    # get index locations of every 1 value in vector
    idx = np.nonzero(vector)[0].tolist()
    # use index locations to pull only +ve positions in minhash
    shingles = minhash[:, idx]
    # find minimum value in each hash vector
    signature = np.min(shingles, axis=1)
    return signature

arr = minhash_arr(vocab, 40)

signatures = []

for vector in shingles_1hot:
    signatures.append(get_signature(arr, vector))

# merge signatures into single array
signatures = np.stack(signatures)
#print(signatures.shape)

print(signatures[0])

# LSH
# Finally, we move onto the LSH process. We will use a class here:

from itertools import combinations

class LSH:
    buckets = []
    counter = 0
    def __init__(self, b):
        self.b = b
        for i in range(b):
            self.buckets.append({})

    def make_subvecs(self, signature):
        l = len(signature)
        assert l % self.b == 0
        r = int(l / self.b)
        # break signature into subvectors
        subvecs = []
        for i in range(0, l, r):
            subvecs.append(signature[i:i+r])
        return np.stack(subvecs)
    
    def add_hash(self, signature):
        subvecs = self.make_subvecs(signature).astype(str)
        for i, subvec in enumerate(subvecs):
            subvec = ','.join(subvec)
            if subvec not in self.buckets[i].keys():
                self.buckets[i][subvec] = []
            self.buckets[i][subvec].append(self.counter)
        self.counter += 1

    def check_candidates(self):
        candidates = []
        for bucket_band in self.buckets:
            keys = bucket_band.keys()
            for bucket in keys:
                hits = bucket_band[bucket]
                if len(hits) > 1:
                    candidates.extend(combinations(hits, 2))
        return set(candidates)

b = 20

lsh = LSH(b)

for signature in signatures:
    lsh.add_hash(signature)

print(lsh.buckets)
# Now we've filled our hash buckets all we need to do is loop through each and where we have multiple entries in a single bucket, mark these as our candidate pairs.

candidate_pairs = lsh.check_candidates()
print(len(candidate_pairs))

print(list(candidate_pairs))

# We now have all of our candidate pairs!
# Optimizing the Bands

# Now let's visualize the actual cosine similarity of our signature vectors against whether we identified the signatures as candidate pairs or not.

# (we will also calculate Jaccard but it's less useful here, try both!)

# from sklearn.metrics.pairwise import cosine_similarity

# def jaccard(a: set, b: set):
#     return len(a.intersection(b)) / len(a.union(b))

# pairs = pd.DataFrame({
#     'x': [],
#     'y': [],
#     'jaccard': [],
#     'cosine': [],
#     'candidate': []
# })

# from tqdm import tqdm

# data_len = shingles_1hot.shape[0]
# chosen = set()
# # take random sample of pairs
# sample_size = 500
# for _ in tqdm(range(sample_size)):
#     x, y = np.random.choice(data_len, 2)
#     if x == y or (x, y) in chosen: continue
#     chosen.add((x, y))
#     vector_x = signatures[x]
#     vector_y = signatures[y]
#     candidate = 1 if (x, y) in candidate_pairs else 0
#     cosine = cosine_similarity([vector_x], [vector_y])[0][0]
#     pairs = pairs.append({
#             'x': x,
#             'y': y,
#             'jaccard': jaccard(set(vector_x), set(vector_y)),
#             'cosine': cosine,
#             'candidate': candidate
#         }, ignore_index=True)

# # add a normalized cosine column for better alignment
# cos_min = pairs['cosine'].min()
# cos_max = pairs['cosine'].max()
# pairs['cosine_norm'] = (pairs['cosine'] - cos_min) / (cos_max - cos_min)

# import matplotlib.pyplot as plt
# import seaborn as sns

# sns.scatterplot(data=pairs, x='cosine', y='candidate', alpha=0.5)
# plt.show()

# # Now, this is an interesting way to visualize our distribution, but we have reason. 
# # We can actually tune our LSH function using b, and we have a formalized function that tells us the probability of identifying a pair as candidate pairs given their similarity. 
# # We calculate this as so:

# def probability(s, r, b):
#     # s: similarity
#     # r: rows (per band)
#     # b: number of bands
#     return 1 - (1 - s**r)**b

# def normalize(x, x_min, x_max):
#     return (x - x_min) / (x_max - x_min)

# # Let's visualize that for our current parameters, alongside our scatter plot.

# b = 25
# r = int(100 / b)
# s_scores = np.arange(0.01, 1, 0.01)
# P_scores = [probability(s, r, b) for s in s_scores]

# sns.lineplot(x=s_scores, y=P_scores)
# sns.scatterplot(data=pairs, x='cosine', y='candidate', alpha=0.1, color='k')
# plt.show()


# b = 25
# r = int(100 / b)
# s_scores = np.arange(0.01, 1, 0.01)
# P_scores = [probability(s, r, b) for s in s_scores]

# sns.lineplot(x=s_scores, y=P_scores)
# sns.scatterplot(data=pairs, x='cosine_norm', y='candidate', alpha=0.1, color='k')
# plt.show()

# # From here we can attempt to modify the similarity threshold t - which is the cut-off point on our similarity axes as to where we would like a given cosine similarity to rate as a candidate pair or not.

# # Let's try a few different band values with our probability formula to see where this balance may be.

# probs = pd.DataFrame({
#     'P': [],
#     's': [],
#     'b': []
# })

# for b in [100, 50, 25, 20, 10, 5, 2]:
#     r = int(100 / b)
#     s_scores = np.arange(0.01, 1, 0.01)
#     P_scores = [probability(s, r, b) for s in s_scores]
#     probs = probs.append(pd.DataFrame({
#         'P': P_scores,
#         's': s_scores,
#         'b': [str(b)]*len(s_scores)
#     }), ignore_index=True)

# sns.lineplot(data=probs, x='s', y='P', hue='b')
# plt.show()
# # So a b value of 20 have us a threshold value t slightly too high (depending on our definition of 'similar'), so maybe we can use b == 25 to get a better distribution of our candidate pairs.

# b = 25

# lsh = LSH(b)

# for signature in signatures:
#     lsh.add_hash(signature)

# candidate_pairs = lsh.check_candidates()
# len(candidate_pairs)

# pairs = pd.DataFrame({
#     'x': [],
#     'y': [],
#     'jaccard': [],
#     'cosine': [],
#     'candidate': []
# })

# data_len = shingles_1hot.shape[0]
# chosen = set()
# # take random sample of pairs
# sample_size = 50_000
# for _ in tqdm(range(sample_size)):
#     x, y = np.random.choice(data_len, 2)
#     if x == y or (x, y) in chosen: continue
#     chosen.add((x, y))
#     vector_x = signatures[x]
#     vector_y = signatures[y]
#     candidate = 1 if (x, y) in candidate_pairs else 0
#     cosine = cosine_similarity([vector_x], [vector_y])[0][0]
#     pairs = pairs.append({
#             'x': x,
#             'y': y,
#             'jaccard': jaccard(set(vector_x), set(vector_y)),
#             'cosine': cosine,
#             'candidate': candidate
#         }, ignore_index=True)

# # add a normalized cosine column for better alignment
# cos_min = pairs['cosine'].min()
# cos_max = pairs['cosine'].max()
# pairs['cosine_norm'] = (pairs['cosine'] - cos_min) / (cos_max - cos_min)

# r = int(100 / b)
# s_scores = np.arange(0.01, 1, 0.01)
# P_scores = [probability(s, r, b) for s in s_scores]

# sns.lineplot(x=s_scores, y=P_scores)
# sns.scatterplot(data=pairs, x='cosine_norm', y='candidate', alpha=0.1, color='k')

# r = int(100 / b)
# s_scores = np.arange(0.01, 1, 0.01)
# P_scores = [probability(s, r, b) for s in s_scores]

# sns.lineplot(x=s_scores, y=P_scores)
# sns.scatterplot(data=pairs, x='cosine_norm', y='candidate', alpha=0.1, color='k')

# # Shifting from b == 20 to b == 25 has reduced the number of non-candidates around 0.7 - 0.8, and we can see that the number of candidate pairs in total has increased significantly too, from 7468 to 19436.

# # Now, in our own use-cases, the preferred similarity threshold will of-course change.

# # It's also worth noting that different similarity metrics will produce different charts:

# r = int(100 / b)
# s_scores = np.arange(0.01, 1, 0.01)
# P_scores = [probability(s, r, b) for s in s_scores]

# sns.lineplot(x=s_scores, y=P_scores)
# sns.scatterplot(data=pairs, x='jaccard', y='candidate', alpha=0.1, color='k')

# plt.show()




