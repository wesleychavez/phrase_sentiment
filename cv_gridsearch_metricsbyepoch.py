import numpy as np 
import pandas as pd
from matplotlib import pyplot as plt
import itertools
import config_grid as config

from sklearn.model_selection import StratifiedKFold

from keras.models import Sequential
from keras.layers import Dense, Embedding, SpatialDropout1D, LSTM, GRU, Bidirectional
from keras.utils.np_utils import to_categorical
from gensim.models.word2vec import Word2Vec

def main():

    train = pd.read_csv('train.tsv', sep="\t")
    test = pd.read_csv('test.tsv', sep="\t")

    # Phrases to lists of words
    train['Phrase'] = train['Phrase'].apply(lambda x: x.lower())
    test['Phrase'] = test['Phrase'].apply(lambda x: x.lower())
    corpus_text_train = '\n'.join(train['Phrase'])
    corpus_text_test = '\n'.join(test['Phrase'])
    phrases_train = corpus_text_train.split('\n')
    phrases_test = corpus_text_test.split('\n')
    phrases_train = [line.lower().split(' ') for line in phrases_train]
    phrases_test = [line.lower().split(' ') for line in phrases_test]
    phrases = phrases_train + phrases_test

    # Create Word2Vec
    word2vec = Word2Vec(sentences=phrases,
                        size=config.w2v_vector_size, 
                        window=config.w2v_window_size,
                        min_count=config.w2v_min_count) 

    pretrained_weights = word2vec.wv.syn0
    vocab_size, embed_dim = pretrained_weights.shape

    # Get corresponding index/word
    def word2idx(word):
        #print (word + ": " + str(word2vec.wv.vocab[word].index))
        return word2vec.wv.vocab[word].index
    def idx2word(idx):
        return word2vec.wv.index2word[idx]

    # Set up training inputs and outputs    
    max_phrase_len = max([len(phrase) for phrase in phrases])
    train_x = np.zeros([len(phrases_train), max_phrase_len], dtype=np.int32)
    train_y = np.zeros([len(phrases_train)], dtype=np.int32)
    
    # Indexes are input to Embedding layer
    for i, phrase in enumerate(phrases_train):
        for t, word in enumerate(phrase):
            train_x[i, t] = word2idx(word)
        train_y[i] = train['Sentiment'][i]

    print('train_x shape:', train_x.shape)
    print('train_y shape:', train_y.shape)

    # Define LSTM model, each LSTM layer has half as many units as the
    # preceding one
    def create_model(layer_type='LSTM', num_layers=1, num_units=128, 
                     dropout=0.1, recurrent_dropout=0.1, spatial_dropout=0.1,
                     optimizer='adam'):
        model = Sequential()
        model.add(Embedding(input_dim=vocab_size, output_dim=embed_dim,
                            weights=[pretrained_weights],
                            input_length=max_phrase_len))
        model.add(SpatialDropout1D(rate=spatial_dropout))
        for i in range(num_layers):
            # Last layer we don't need to return sequences
            if(i==num_layers-1):
                # Halve the number of units for every layer added
                if (layer_type == 'LSTM' or layer_type == 'lstm'):
                    model.add(LSTM(int(num_units/(2**i)), dropout=dropout, 
                                   recurrent_dropout=recurrent_dropout))
                elif (layer_type == 'GRU' or layer_type == 'gru'):
                    model.add(GRU(int(num_units/(2**i)), dropout=dropout, 
                                  recurrent_dropout=recurrent_dropout))
                elif (layer_type == 'BILSTM' or layer_type == 'bilstm'):
                    model.add(Bidirectional(LSTM(int(num_units/(2**i)), dropout=dropout, 
                                                 recurrent_dropout=recurrent_dropout)))
                elif (layer_type == 'BIGRU' or layer_type == 'bigru'):
                    model.add(Bidirectional(GRU(int(num_units/(2**i)), dropout=dropout, 
                                                 recurrent_dropout=recurrent_dropout)))
            else:
                if (layer_type == 'LSTM' or layer_type == 'lstm'):
                    model.add(LSTM(int(num_units/(2**i)), dropout=dropout, 
                                   recurrent_dropout=recurrent_dropout,
                                   return_sequences=True))
                elif (layer_type == 'GRU' or layer_type == 'gru'):
                    model.add(GRU(int(num_units/(2**i)), dropout=dropout, 
                                  recurrent_dropout=recurrent_dropout,
                                  return_sequences=True))
                elif (layer_type == 'BILSTM' or layer_type == 'bilstm'):
                    model.add(Bidirectional(LSTM(int(num_units/(2**i)), dropout=dropout, 
                                                 recurrent_dropout=recurrent_dropout,
                                                 return_sequences=True)))
                elif (layer_type == 'BIGRU' or layer_type == 'bigru'):
                    model.add(Bidirectional(GRU(int(num_units/(2**i)), dropout=dropout, 
                                                recurrent_dropout=recurrent_dropout,
                                                return_sequences=True)))
        model.add(Dense(5,activation='softmax'))
        model.compile(loss='categorical_crossentropy', optimizer=optimizer,
                      metrics=['accuracy'])
        print(model.summary())
        return model

    # Hyperparameters to cross-validate
    param_grid = [config.layer_type, config.num_layers, config.num_units,
                  config.dropout, config.recurrent_dropout,
                  config.spatial_dropout, config.optimizer, config.batch_size]
    # Hyperparameter grid
    combos = list(itertools.product(*param_grid))

    # Metrics arrays
    accuracies = np.zeros((len(combos), config.k, config.epochs))
    losses = np.zeros((len(combos), config.k, config.epochs))
    val_accuracies = np.zeros((len(combos), config.k, config.epochs))
    val_losses = np.zeros((len(combos), config.k, config.epochs))

    # Loop over k folds of training/testing data
    skf = StratifiedKFold(n_splits=config.k, shuffle=True, random_state=123)
    k_iter = -1
    for train_index, test_index in skf.split(train_x, train_y):
        k_iter = k_iter + 1
        x_train, x_test = train_x[train_index], train_x[test_index]
        y_train, y_test = train_y[train_index], train_y[test_index]
        y_train = to_categorical(y_train)
        y_test = to_categorical(y_test)

        # Grid Search, plotting cross-validation scores by epoch
        for i in range(len(combos)):

            model = create_model(layer_type=combos[i][0], num_layers=combos[i][1],
                                 num_units=combos[i][2], dropout=combos[i][3], 
                                 recurrent_dropout=combos[i][4],
                                 spatial_dropout=combos[i][5],optimizer=combos[i][6])

            history = model.fit(x=x_train, y=y_train, batch_size=combos[i][7],
                      epochs=config.epochs, validation_data=(x_test,y_test))
            print(history.history['val_acc'])
            accuracies[i,k_iter,:] = history.history['acc']
            losses[i,k_iter,:] = history.history['loss']
            val_accuracies[i,k_iter,:] = history.history['val_acc']
            val_losses[i,k_iter,:] = history.history['val_loss']
            print (val_accuracies)
    
    # Mean and std across k folds
    mean_acc = np.mean(accuracies,axis=1)
    mean_val_acc = np.mean(val_accuracies,axis=1)
    mean_loss = np.mean(losses,axis=1)
    mean_val_loss = np.mean(val_losses,axis=1)
    std_acc = np.std(accuracies,axis=1)
    std_val_acc = np.std(val_accuracies,axis=1)
    std_loss = np.std(losses,axis=1)
    std_val_loss = np.std(val_losses,axis=1)

    # Write these mean and stds to file organized by hyperparameter combination
    f = open("Metrics.txt","a")
    for i in range(len(combos)):
        f.write('-------------------------')
        f.write('\n')
        f.write(str(combos[i]))
        f.write('\n')
        f.write('-------------------------')
        f.write('\n')
        f.write('accuracy')
        f.write('\n')
        np.savetxt(f, mean_acc[i], delimiter=",", fmt='%.4f')
        f.write('std')
        f.write('\n')
        np.savetxt(f, std_acc[i], delimiter=",", fmt='%.4f')
        f.write('validation accuracy')
        f.write('\n')
        np.savetxt(f, mean_val_acc[i], delimiter=",", fmt='%.4f')
        f.write('std')
        f.write('\n')
        np.savetxt(f, std_val_acc[i], delimiter=",", fmt='%.4f')
        f.write('loss')
        f.write('\n')
        np.savetxt(f, mean_loss[i], delimiter=",", fmt='%.4f')
        f.write('std')
        f.write('\n')
        np.savetxt(f, std_loss[i], delimiter=",", fmt='%.4f')
        f.write('validation loss')
        f.write('\n')
        np.savetxt(f, mean_val_loss[i], delimiter=",", fmt='%.4f')
        f.write('std')
        f.write('\n')
        np.savetxt(f, std_val_loss[i], delimiter=",", fmt='%.4f')
    f.close()

    # Plot accuracies/losses for each hyperparameter combination
    # Each data point plotted is an average across the k folds.
    for i in range(len(combos)):
        fig, ax = plt.subplots(1,2)
        ax[0].errorbar(range(len(mean_acc[i])), mean_acc[i], yerr=std_acc[i])
        ax[0].errorbar(range(len(mean_val_acc[i])), mean_val_acc[i], yerr=std_val_acc[i])
        ax[0].set_title('Model Accuracy')
        ax[0].set_ylabel('Accuracy')
        ax[0].set_xlabel('Epoch')
        ax[0].legend(['Train', 'Val'], loc='upper left')

        ax[1].errorbar(range(len(mean_loss[i])), mean_loss[i], yerr=std_loss[i])
        ax[1].errorbar(range(len(mean_val_loss[i])), mean_val_loss[i], yerr=std_val_loss[i])
        ax[1].set_title('Model Loss')
        ax[1].set_ylabel('Loss')
        ax[1].set_xlabel('Epoch')
        ax[1].legend(['Train', 'Val'], loc='upper left')

        out_name = str(combos[i])
        out_name = out_name.replace(" ", "")
        out_name = out_name.replace("'", "")
        out_name = out_name.replace("(", "_")
        out_name = out_name.replace(")", "_")
        out_name = out_name.replace(",", "_")
        fig.savefig(out_name + '_accuracyandloss.png')

    # Highest accuracy after training, not by epoch
    mean_val_acc_bymodel = np.mean(val_accuracies[:,:,-1],axis=1)
    print('Model with hightest mean validation accuracy:')
    print (combos[np.argmax(mean_val_acc_bymodel)])
    print (np.max(mean_val_acc_bymodel))
    print ('------------------------------')
    for i in range(len(mean_val_acc_bymodel)):
        print(combos[i])
        print(mean_val_acc_bymodel[i])
if __name__ == '__main__':
    main()
