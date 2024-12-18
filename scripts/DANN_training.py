import os
import sys
import keras
import tensorflow as tf 
import numpy as np 
import pandas as pd 
from keras.models import Model
from keras.optimizers import Adam
from keras.initializers import RandomNormal
from keras.layers import Conv1D, Dense, Flatten, AveragePooling1D, Reshape, BatchNormalization, Normalization, Dropout, Conv1DTranspose
from keras.layers import Input, LeakyReLU, Activation, Concatenate
from tensorflow.keras import models
from sklearn.utils import shuffle
from sklearn.metrics import accuracy_score
from keras.utils import plot_model

os.environ['TF_ENABLE_ONEDNN_OPTS'] = '0'

class GDANN(models.Model):
    '''
    Define the GDAN architecture
    '''
    def __init__(self, no_features, no_domain_classes = 5, task = 'binary_classification'):
        super(GDANN, self).__init__()
        self.task = task
        self.no_features = no_features
        input_shape = (no_features, 1)
        self.feature_extractor, feature_extractor_output = self.build_feature_extractor(input_shape)
        self.label_classifier = self.build_label_classifier(feature_extractor_output)
        self.discriminator = self.build_domain_discriminator(data_shape=(feature_extractor_output,1), n_classes=no_domain_classes)
        self.generator = self.build_generator(input_shape=(feature_extractor_output,1), n_classes= no_domain_classes)
        self.gan_model = self.build_gan(self.generator, self.discriminator, data_shape = (feature_extractor_output,1))
        
    def build_feature_extractor(self, input_shape):
        model = keras.models.Sequential()
        model.add(Input(input_shape))
        model.add(Conv1DTranspose(32, kernel_size=6, strides=2, input_shape = input_shape, activation='relu'))# kernel_regularizer=l2(self.regularization_coeff)
        model.add(BatchNormalization())
        model.add(Conv1DTranspose(64, kernel_size=8, strides=4, activation='relu'))
        model.add(BatchNormalization())
        model.add(Conv1D(32, kernel_size=6, strides=14, activation='relu'))
        model.add(Flatten())
        model.add(Reshape((256, 1)))
        model.add(AveragePooling1D(pool_size=37, strides=20))
        model.add(Flatten())
        model.add(Dense(11, input_shape = input_shape))
        model.add(Normalization(mean = np.zeros(11), variance= np.ones(11)))
        #model.summary()
        optimizer = tf.keras.optimizers.Adam()
        model.compile(optimizer=optimizer)
        ### Tune pool_size and strides according to output = (len(flatten) + 1 - pool_size) / stride
        output_shape = model.output_shape[1]
        plot_model(model, to_file='feature_extractor.png', show_shapes=True, show_layer_names=True)
        return model, output_shape
    
    def build_label_classifier(self, input_shape):
        if self.task == 'binary_classification':
            model = tf.keras.Sequential()
            model.add(Input((input_shape,)))
            model.add(Dense(256,activation= 'relu')) # kernel_regularizer=l2(self.regularization_coeff)
            model.add(Dense(512,activation='relu')) # , kernel_regularizer=l2(self.regularization_coeff)
            model.add(Dense(64,activation='relu'))
            model.add(Dense(1, activation='sigmoid'))
            optimizer = tf.keras.optimizers.Adam()
            model.compile(optimizer=optimizer, loss='binary_crossentropy', metrics = ['accuracy'])
            plot_model(model, to_file='label_classifier.png', show_shapes=True, show_layer_names=True)
            #model.summary()
        return model
    
    def build_domain_discriminator(self, data_shape = (11,1), n_classes = 10):
        # generic features extracted representation always real 
        in_src_dist = Input(shape=data_shape, name='timestamp_0')
        # original distribution of timestep 0 either fake or real 
        in_target_dist = Input(shape=data_shape, name = 'features')
        merge = Concatenate()([in_src_dist, in_target_dist])
        # concatenate images channel-wise
        merge = Dense(64, activation='leaky_relu')(merge)
        merge = BatchNormalization()(merge)
        merge = Dropout(0.25)(merge)
        merge = Dense(128, activation='leaky_relu')(merge)
        merge = Dropout(0.25)(merge)
        merge = Dense(512, activation='leaky_relu')(merge)
        merge = Dropout(0.25)(merge)
        merge = Dense(512, activation='leaky_relu')(merge)
        #real/fake output
        merge = Flatten()(merge)
        out1 = Dense(1, activation='sigmoid', name = 'real_fake')(merge)
        # class output
        out2 = Dense(n_classes, activation='sigmoid', name = 'category')(merge)
        # define model
        model = Model([in_src_dist, in_target_dist], [out1, out2])
        # compile model
        opt = Adam(learning_rate=0.0001)
        #model.summary()
        model.compile(
            loss ={'real_fake':'binary_crossentropy', 'category':'sparse_categorical_crossentropy'},
            optimizer=opt, metrics = ['accuracy', 'accuracy'])
        
        plot_model(model, to_file='discriminator.png', show_shapes=True, show_layer_names=True)
        
        return model

    def build_generator(self, input_shape, n_classes=10):
        init = RandomNormal(stddev=0.02)
        # image generator input
        in_datapoint = Input(shape=input_shape)
        # foundation for a 11x1 datapoint, first no is number of feature maps
        n_nodes = 64
        gen = Dense(n_nodes, kernel_initializer=init)(in_datapoint)
        #gen = Activation('relu')(gen)
        gen = LeakyReLU()(gen)
        gen = Conv1DTranspose(128, kernel_size=4, strides=2)(gen)
        gen = LeakyReLU()(gen)
        gen = BatchNormalization()(gen)
        gen = Conv1DTranspose(256, kernel_size=4, strides=4)(gen)
        gen = LeakyReLU()(gen)
        gen = BatchNormalization()(gen)
        gen = Conv1DTranspose(256, kernel_size=4, strides=4)(gen)
        gen = LeakyReLU()(gen)
        gen = BatchNormalization()(gen)
        gen = Conv1D(256, kernel_size=8, strides=4)(gen)
        gen = LeakyReLU()(gen)
        gen = BatchNormalization()(gen)
        gen = Conv1D(128, kernel_size = 6, strides=2)(gen)
        gen = LeakyReLU()(gen)
        gen = BatchNormalization()(gen)
        gen = Conv1D(128, kernel_size = 4, strides=2)(gen)
        gen = LeakyReLU()(gen)
        gen = BatchNormalization()(gen)
        gen = Flatten()(gen)
        gen = Dense(11)(gen)
        out_layer = Activation('linear')(gen)
        model = Model([in_datapoint], out_layer)
        plot_model(model, to_file='generator.png', show_shapes=True, show_layer_names=True)
        return model
    
    def build_gan(self, g_model, d_model, data_shape):
        # define the source image
        in_src = Input(shape=data_shape)
        # connect the source image to the generator input
        gen_out = g_model([in_src])
        # connect the source input and generator output to the discriminator input
        dis_output = d_model([gen_out, in_src])
        # define gan model as taking noise and label and outputting real/fake and label outputs
        model = Model(inputs = [in_src], outputs = [dis_output[0], dis_output[1], gen_out])
        # compile model
        opt = Adam(learning_rate=0.001)
        model.compile(loss=['binary_crossentropy','sparse_categorical_crossentropy','mae'], optimizer=opt)
        model.summary()
        return model

# select real samples
def generate_real_samples(dataset, first_dist, len_single_domain, c_labels, d_labels, n_samples):
    '''
    Sample real samples from the t_0 and pair it with the correct class and domain labels
    dataset: np.array
        a np.array containing the concatenated t_0 and t_1
    first_dist: np.array
        a np.array containing the points from distribution 0 (t_0)
    len_single_domain: int 
    c_labels: np.array 
        an array with combined ground truths 
    d_labels: np.array 
        an array with combined domain labels i.e either original dist or a one 
        influenced by the drift 
    n_samples: int
        the number of points that has to be generated 
    '''
    # Generate random indices
    random_indices = np.random.choice(range(len(dataset)), n_samples)
    datapoints = np.array([dataset[idx] for idx in random_indices])
    #Find corresponding indices in the original dataset
    og_indices = random_indices % len_single_domain
    original_datapoints = first_dist[og_indices]
    # Same for class and domain labels 
    class_labels = np.array([c_labels[idx] for idx in random_indices])
    domain_labels = np.array([d_labels[idx] for idx in random_indices])

    return datapoints, original_datapoints, class_labels, domain_labels

    
def train_architecture(model,first_dist, data, labels,lam = 100, lambda_2 = 1,  num_epochs = 100, batch_size = 1024, feature_extractor_training_time = 350):
    '''
    Train the GDAN architecture, defined in GDANN.

    Parameters
    --------
        model: GDANN class 
            a class which defines the architecture, the parameters of each network 
        first_dist: np.array
            the array of t_0 data distribution used for matching points 1-to-1 or randomly 
        data: list of np.arrays
            a list with numpy arrays, containing the distributions of data used for training 
            i.e. t_0 and t_1 
        labels: list of np.arrays
            a list of numpy arrays alike the point above, but including ground truth instead
            of feature data 
        lam: float 
            hyperparemeter regulating the degree of penaliation of the generator 
            for producing instances which are located far away from t_0 
        lambda_2: float 
            hyperparameter regulating the loss of the feature extractor, modelling the 
            dependance between feature extractor and the discriminator 
        num_epochs: int 
            number of epochs during training 
        batch_size: int 
        feature_extractor_training_time: int 
            hyperparameter
            the number of steps for which the generator updates are switched off, 
            the number of steps for which the feature extractor is trained
    
    Outputs
    --------
        saves the model weights to a h5 file 
        saves the learning curves into a csv file
    '''
    domain_labels = []
    iterations_data = []

    #Create an array that combines data from t_0 and t_1 generate domain labels 
    len_single_domain = len(data[0])
    for i, datapoints in enumerate(data):
        domain_labels.extend([i] * len(datapoints))
    
    combined_domain_labels = np.array(domain_labels)   
    combined_data = np.concatenate(data)
    combined_class_labels = np.concatenate(labels) 
    
    #calculate the number of batches per training epoch
    bat_per_epo = int(len(combined_data) / batch_size)
	# calculate the number of training iterations
    n_steps = bat_per_epo * num_epochs
	# calculate the size of half a batch of samples
    half_batch = int(batch_size / 2)

	# Enumerate through epochs
    for i in range(n_steps):
        print(f"Step no {i}/{n_steps}")
        # get randomly selected 'real' samples
        datapoints, original_points,class_labels, domain_labels  = generate_real_samples(combined_data,first_dist, len_single_domain, combined_class_labels, combined_domain_labels, half_batch)

        with tf.GradientTape() as feature_extractor_tape, tf.GradientTape() as label_classifier_tape: 
            # Pass forward through the discriminator
            with tf.GradientTape() as discriminator_tape: 
                #Make sure the discriminator is trainable
                for layer in model.discriminator.layers:
                    if not isinstance(layer, BatchNormalization):
                        layer.trainable = True
                
                domain_labels_tensor = tf.convert_to_tensor(domain_labels)

                #Train discriminator on real distributions
                features = model.feature_extractor(datapoints)
                discriminator_output = model.discriminator([tf.convert_to_tensor(original_points), features])
                binary_loss_real = tf.keras.losses.binary_crossentropy(tf.ones_like(discriminator_output[0]), discriminator_output[0])
                category_loss_real = tf.keras.losses.binary_crossentropy(tf.reshape(domain_labels_tensor, (-1,1)), discriminator_output[1])
                
                #Train discriminator on generated distributions
                generated_t0 = model.generator([features])
                discriminator_output_fake = model.discriminator([generated_t0, features])
                binary_loss_fake = tf.keras.losses.binary_crossentropy(tf.zeros_like(discriminator_output_fake[0]) , discriminator_output_fake[0])
                category_loss_fake = tf.keras.losses.binary_crossentropy(tf.reshape(domain_labels_tensor, (-1,1)), discriminator_output_fake[1])

                #Calculte the combined discriminator's loss
                discriminators_loss = tf.reduce_mean(binary_loss_real + category_loss_real + binary_loss_fake + category_loss_fake)
            
            #Update weights of the discriminator
            discriminators_trainable_vars = model.discriminator.trainable_variables
            grads = discriminator_tape.gradient(discriminators_loss, discriminators_trainable_vars)
            model.discriminator.optimizer.apply_gradients(zip(grads, discriminators_trainable_vars))
            
            #Pass forward through the generator
            with tf.GradientTape() as generator_tape: 

                for layer in model.discriminator.layers:
                    if not isinstance(layer, BatchNormalization):
                        layer.trainable = False

                #Generate generator and discriminator's outputs 
                generated_t0 = model.generator([features])
                discriminator_output = model.discriminator([generated_t0, features])

                #Calculate loss functions 
                generator_binary_loss = tf.keras.losses.binary_crossentropy(tf.ones_like(discriminator_output[0]), discriminator_output[0])
                generator_category_loss = tf.keras.losses.binary_crossentropy(tf.reshape(tf.convert_to_tensor(domain_labels),(-1,1)),discriminator_output[1])
                mae_between_distributions = tf.reduce_mean(tf.abs(original_points - generated_t0), axis = 1)
                generator_loss = tf.reduce_mean(generator_binary_loss + generator_category_loss) + lam * mae_between_distributions
                
                #If the generator updates can be switched on update the weights of the generator
                if i > feature_extractor_training_time:       
                    generator_trainable_vars = model.gan_model.trainable_variables
                    grads = generator_tape.gradient(generator_loss, generator_trainable_vars)
                    model.gan_model.optimizer.apply_gradients(zip(grads, generator_trainable_vars))

            #Generate label predictions and calculate losses for label classifier and feature extractor 
            label_pred = model.label_classifier(features)
            label_loss = tf.keras.losses.binary_crossentropy(class_labels.reshape(-1,1), label_pred)
            encoder_loss = tf.reduce_mean(label_loss - lambda_2 * (category_loss_real + category_loss_fake))
        
        #If i <= k, calculate gradient for LC and F and update the weights of the networks
        if i <= feature_extractor_training_time:
            trainable_vars_enc = model.feature_extractor.trainable_variables
            trainable_vars_task = model.label_classifier.trainable_variables
            gradients_label_classifier = label_classifier_tape.gradient(label_loss, trainable_vars_task)
            gradients_feature_extractor = feature_extractor_tape.gradient(encoder_loss, trainable_vars_enc)

            model.label_classifier.optimizer.apply_gradients(zip(gradients_label_classifier, trainable_vars_task))
            model.feature_extractor.optimizer.apply_gradients(zip(gradients_feature_extractor, trainable_vars_enc))
       
        #Basically end of the training loop for the architecture from now only verification of results on training set
        # Compute metrics on the training sets
        if i % 25 == 0 and i !=0 :
            if i == 25:
                #For the learning curves draw random 20 percent of the dataframe 
                num_points_20_percent = int(0.2 * len(combined_data))
                random_indices = np.random.choice(len(combined_data), num_points_20_percent, replace=False)

            test_data = combined_data[random_indices]
            test_domain_labels = combined_domain_labels[random_indices]
            test_class_labels = combined_class_labels[random_indices]
            features = model.feature_extractor(test_data)

            predicted_class_labels_probabilities = model.label_classifier(features)
            predicted_class_labels = tf.cast(predicted_class_labels_probabilities >= 0.5, tf.int32)
            train_accuracy_class = accuracy_score(test_class_labels, predicted_class_labels)

            generated_t0 = model.generator([features])
            disc_output = model.discriminator([generated_t0, features])
            predicted_domain_probabilities = disc_output[1]
            predicted_domain_class = tf.cast(predicted_domain_probabilities >= 0.5, tf.int32)

            train_accuracy_domain = accuracy_score(predicted_domain_class, test_domain_labels)

            # Sample data for one iteration
            iteration_data = {
                "Probabilities": predicted_domain_probabilities,
                "Predicted labels": predicted_domain_class,
                "Domain_Classification_Accuracy": train_accuracy_domain,
                "Step number": i,
                "Generator mae loss": tf.reduce_mean(generator_loss).numpy(),
                "Generator real/fake loss": tf.reduce_mean(generator_binary_loss).numpy(),
                "Generator category loss": tf.reduce_mean(generator_category_loss).numpy(),
                "Discriminator loss": tf.reduce_mean(discriminators_loss).numpy(),
                "Label loss": tf.reduce_mean(label_loss).numpy(),
                "Class accuracy": train_accuracy_class,
                "Disc real loss": tf.reduce_mean(binary_loss_real).numpy(),
                "Disc fake loss": tf.reduce_mean(binary_loss_fake).numpy(),
                "Disc category loss real": tf.reduce_mean(category_loss_real).numpy(),
                "Disc category loss fake": tf.reduce_mean(category_loss_fake).numpy()
            }

            iterations_data.append(iteration_data)

    # Convert the created lists to a DataFrame
    dfs = []
    for i, iteration in enumerate(iterations_data):
        print("Iteration Probabilities", iteration["Probabilities"])
        df = pd.DataFrame(iteration["Probabilities"], columns=[f"Probability_{j+1}" for j in range(len(iteration["Probabilities"][0]))])
        df['Predicted labels'] = iteration['Predicted labels']
        df['Domain_Classification_Accuracy'] = iteration["Domain_Classification_Accuracy"]
        df['Step number'] = iteration["Step number"]
        df['Generator mae loss'] = iteration["Generator mae loss"]
        df['Generator real/fake loss'] = iteration['Generator real/fake loss']
        df['Generator class loss'] = iteration['Generator category loss']
        df['Dicriminator loss'] = iteration["Discriminator loss"]
        df['Label loss'] = iteration['Label loss']
        df['Class accuracy'] = iteration['Class accuracy']
        df['Disc real loss'] = iteration['Disc real loss']
        df['Disc fake loss'] = iteration ['Disc fake loss']
        df['Disc category loss real'] = iteration['Disc category loss real']
        df['Disc category loss fake'] = iteration['Disc category loss fake']
        dfs.append(df)

    concatenated_df = pd.concat(dfs, ignore_index=True)
    concatenated_df.to_csv('concatenated_dataframe.csv', index=False)

    save_path = f'./GDANN_arch.weights.h5' 
    model.save_weights(save_path)
    print("Training finished.")

        