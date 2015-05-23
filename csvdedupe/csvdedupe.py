#! /usr/bin/env python

import os
import sys
import logging
from cStringIO import StringIO

import csvhelpers
import dedupe

import itertools


class CSVDedupe(csvhelpers.CSVCommand) :
    def __init__(self):
        super(CSVDedupe, self).__init__()

        # set defaults
        try:
            # take in STDIN input or open the file
            if isinstance(self.configuration['input'], file):
                if not sys.stdin.isatty():
                    self.input = self.configuration['input'].read()
                    # We need to get control of STDIN again.
                    # This is a UNIX/Mac OSX solution only
                    # http://stackoverflow.com/questions/7141331/pipe-input-to-python-program-and-later-get-input-from-user
                    # 
                    # Same question has a Windows solution
                    sys.stdin = open('/dev/tty')  # Unix only solution,
                else:
                    raise self.parser.error("No input file or STDIN specified.")
            else:
                try:
                    self.input = open(self.configuration['input'], 'rU').read()
                except IOError:
                    raise self.parser.error("Could not find the file %s" %
                                            (self.configuration['input'], ))
        except KeyError:
            raise self.parser.error("No input file or STDIN specified.")

        if self.field_definition is None :
            try:
                self.field_names = self.configuration['field_names']
                self.field_definition = [{'field': field,
                                          'type': 'String'}
                                         for field in self.field_names]
            except KeyError:
                raise self.parser.error("You must provide field_names")
        else :
            self.field_names = [self.field_def['field'] 
                                for field_def in self.field_definitions]

        self.destructive = self.configuration.get('destructive', False)

    def add_args(self) :
        # positional arguments
        self.parser.add_argument('input', nargs='?', default=sys.stdin,
            help='The CSV file to operate on. If omitted, will accept input on STDIN.')
        self.parser.add_argument('--destructive', action='store_true',
            help='Output file will contain unique records only')


    def main(self):

        data_d = {}
        # import the specified CSV file

        data_d = csvhelpers.readData(self.input, self.field_names)

        logging.info('imported %d rows', len(data_d))

        # sanity check for provided field names in CSV file
        for field in self.field_definition:
            if field['type'] != 'Interaction':
                if not field['field'] in data_d[0]:

                    raise parser.error("Could not find field '" +
                                       field['field'] + "' in input")

        logging.info('using fields: %s' % [field['field']
                                           for field in self.field_definition])
        # # Create a new deduper object and pass our data model to it.
        deduper = dedupe.Dedupe(self.field_definition)

        # Set up our data sample
        logging.info('taking a sample of %d possible pairs', self.sample_size)
        deduper.sample(data_d, self.sample_size)

        # If we have training data saved from a previous run of dedupe,
        # look for it an load it in.
        # __Note:__ if you want to train from scratch, delete the training_file

        if os.path.exists(self.training_file):
            logging.info('reading labeled examples from %s' %
                         self.training_file)
            with open(self.training_file) as tf:
                deduper.readTraining(tf)
        elif self.skip_training:
            raise parser.error(
                "You need to provide an existing training_file or run this script without --skip_training")

        if not self.skip_training:
            logging.info('starting active labeling...')

            dedupe.consoleLabel(deduper)

            # When finished, save our training away to disk
            logging.info('saving training data to %s' % self.training_file)
            with open(self.training_file, 'w') as tf:
                deduper.writeTraining(tf)
        else:
            logging.info('skipping the training step')

        deduper.train()

        # ## Blocking

        logging.info('blocking...')

        # ## Clustering

        # Find the threshold that will maximize a weighted average of our precision and recall. 
        # When we set the recall weight to 2, we are saying we care twice as much
        # about recall as we do precision.
        #
        # If we had more data, we would not pass in all the blocked data into
        # this function but a representative sample.

        logging.info('finding a good threshold with a recall_weight of %s' %
                     self.recall_weight)
        threshold = deduper.threshold(data_d, recall_weight=self.recall_weight)

        # `duplicateClusters` will return sets of record IDs that dedupe
        # believes are all referring to the same entity.

        logging.info('clustering...')
        clustered_dupes = deduper.match(data_d, threshold)

        logging.info('# duplicate sets %s' % len(clustered_dupes))

        write_function = csvhelpers.writeResults
        # write out our results
        if self.destructive:
            write_function = csvhelpers.writeUniqueResults

        if self.output_file:
            with open(self.output_file, 'w') as output_file:
                write_function(clustered_dupes, self.input, output_file)
        else:
            write_function(clustered_dupes, self.input, sys.stdout)


def launch_new_instance():
    d = CSVDedupe()
    d.main()


if __name__ == "__main__":
    launch_new_instance()
