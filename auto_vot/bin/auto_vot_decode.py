#! /usr/bin/env python

"""
auto_vot_decode.py

Use an existing classifier to measure VOT for stops in a set of
textgrids and corresponding wav files. Run with -h argument for
information on arguments, and see documentation for usage examples.

Author: Joseph Keshet, 18/11/2013
"""

import argparse
import os
import tempfile
import shutil

from auto_vot_extract_features import *
from autovot.utilities import *
from autovot.textgrid import *


if __name__ == "__main__":
    # parse arguments
    parser = argparse.ArgumentParser(description='Use an existing classifier to measure VOT for stops in a set of '
                                                 'textgrids and corresponding wav files.')
    parser.add_argument('wav_filenames', default='', help="Text file listing  WAV files")
    parser.add_argument('textgrid_filenames', default='', help="Text file listing corresponding manually labeled "
                                                               "TextGrid files containing stops VOT is to measured for")
    parser.add_argument('model_filename', help="Name of classifier to be used to measure VOT")
    parser.add_argument('--vot_tier', help='Name of the tier containing manually labeled VOTs to compare automatic '
                                           'measurements to (optional. default is none)', default='')
    parser.add_argument('--vot_mark', help='On vot_tier, only intervals with this mark value (e.g. "vot", "pos", '
                                           '"neg") are used, or "*" for any string (this is the default)', default='*')
    parser.add_argument('--window_tier', help='Name of the tier containing windows to be searched as possible starts'
                                              'of the predicted VOT (default: none). If not given *and* vot_tier given'
                                              ', a window with boundaries window_min and window_max to the left and '
                                              'right of the manually labeled VOT will be used . NOTE: either window_tier'
                                              ' or vot_tier must be specified. If both are specified, window_tier is '
                                              'used, and window_min and window_max are ignored.', default='')
    parser.add_argument('--window_mark', help='VOT is only predicted for intervals on the window tier with this mark '
                                              'value (e.g. "vot", "pos", "neg"), or "*" for any string (this is the '
                                              'default)', default='*')
    parser.add_argument('--window_min', help='Left boundary of the window (in msec) relative to the VOT '
                                             'interval\'s left boundary.', default=-50, type=float)
    parser.add_argument('--window_max', help='Right boundary of the window (in msec) relative to the VOT interval\'s'
                        ' right boundary. Usually should be positive, that is, after the VOT interval\'s right '
                        'boundary. (default: %(default)s)', default=800, type=float)
    parser.add_argument('--min_vot_length', help='Minimum allowed length of predicted VOT (in msec) (default: '
                                                 '%(default)s)', default=15, type=int)
    parser.add_argument('--max_vot_length', help='Maximum allowed length of predicted VOT (in msec) (default: '
                        '%(default)s)', default=250, type=int)
    parser.add_argument('--max_num_instances', default=0, type=int, help='Maximum number of instances per file to use '
                                                                         '(default: use everything)')
    parser.add_argument('--ignore_existing_tiers', help='add a new AutoVOT tier to output textgrids, even if one '
                                                        'already exists (default: don\'t do so)',
                        action='store_const', const=True, default=False)
    parser.add_argument("--logging_level", help="Level of verbosity of information printed out by this program ("
                                                "DEBUG, INFO, WARNING or ERROR), in order of increasing verbosity. "
                                                "See http://docs.python.org/2/howto/logging for definitions. ("
                                                "default: %(default)s)", default="INFO")
    args = parser.parse_args()

    logging_defaults(args.logging_level)

    # extract tier definitions
    tier_definitions = TierDefinitions()
    args.window_min /= 1000.0   # convert msec to seconds
    args.window_max /= 1000.0   # convert msec to seconds
    tier_definitions.extract_definition(args)

    if is_valid_wav(args.wav_filenames) and is_textgrid(args.textgrid_filenames):
        logging.info("Input arguments consist of a single WAV and a single TextGrid.")
        wav_files = [args.wav_filenames]
        textgrid_files = [args.textgrid_filenames]
    elif is_valid_wav(args.wav_filenames) and not is_textgrid(args.textgrid_filenames):
        logging.error("%s valid WAV file while %s is not a valid TextGrid." % (args.wav_filenames,
                                                                               args.textgrid_filenames))
        exit()
    elif not is_valid_wav(args.wav_filenames) and is_textgrid(args.textgrid_filenames):
        logging.error("%s not valid WAV file while %s is a valid TextGrid." % (args.wav_filenames,
                                                                               args.textgrid_filenames))
        exit()
    else:
        if num_lines(args.wav_filenames) != num_lines(args.textgrid_filenames):
            logging.error("The files %s and %s should have the same number of lines" % (args.wav_filenames,
                                                                                        args.textgrid_filenames))
            exit()

        f = open(args.wav_filenames)
        wav_files = f.readlines()
        f.close()

        f = open(args.textgrid_filenames)
        textgrid_files = f.readlines()
        f.close()

    problematic_files = list()

    # run over files
    for wav_file, textgrid_file in zip(wav_files, textgrid_files):

        wav_file = wav_file.strip()
        textgrid_file = textgrid_file.strip()

        if wav_file == "" or textgrid_file == "":
            continue

        # intermediate files that will be used to represent the locations of the VOTs, their windows and the features
        working_dir = tempfile.mkdtemp()
        features_dir = working_dir + "/features"
        my_basename = os.path.splitext(os.path.basename(wav_file))[0]
        my_basename = working_dir + "/" + my_basename
        os.makedirs(features_dir)
        input_filename = my_basename + ".input"
        features_filename = my_basename + ".feature_filelist"
        labels_filename = my_basename + ".labels"
        preds_filename = my_basename + ".preds"
        final_vot_filename = my_basename + ".vot"

        textgrid_list = my_basename + ".tg_list"
        f = open(textgrid_list, 'w')
        f.write(textgrid_file + '\n')
        f.close()

        wav_list = my_basename + ".wav_list"
        f = open(wav_list, 'w')
        f.write(wav_file + '\n')
        f.close()

        logging.debug("working_dir=%s" % working_dir)

        logging.debug("%s, %s" % (textgrid_list, wav_list))
        logging.debug("%s" % input_filename)

        # call front end (extract features)
        problematic_file = textgrid2front_end(textgrid_list, wav_list, input_filename, features_filename,
                                         features_dir, tier_definitions, decoding=True)
        if len(problematic_file):
            problematic_files += problematic_file
            continue
        
        cmd_vot_front_end = 'VotFrontEnd2 -verbose %s %s %s %s' % (args.logging_level, input_filename, features_filename,
                                                                   labels_filename)
        easy_call(cmd_vot_front_end)

        # decoding (i.e., generate VOT predictions)
        cmd_vot_decode = 'InitialVotDecode -verbose %s -max_onset 200 -min_vot_length %d -max_vot_length %d ' \
                         '-output_predictions %s %s %s %s' % (args.logging_level, args.min_vot_length,
                                                              args.max_vot_length, preds_filename, features_filename,
                                                              labels_filename, args.model_filename)
        easy_call(cmd_vot_decode)

        # convert decoding back to TextGrid
        xmin_proc_win = list()
        xmax_proc_win = list()
        for line in open(input_filename):
            items = line.strip().split()
            xmin_proc_win.append(float(items[1]))
            xmax_proc_win.append(float(items[2]))

        # convert decoding back to TextGrid. first generate list of xmin, xmax and mark
        xmin_preds = list()
        xmax_preds = list()
        mark_preds = list()
        k = 0
        for line in open(preds_filename):
            (confidence, xmin, xmax) = line.strip().split()
            xmin = float(xmin)
            xmax = float(xmax)
            if xmin < xmax:  # positive VOT
                xmin_preds.append(xmin_proc_win[k] + xmin/1000)
                xmax_preds.append(xmin_proc_win[k] + xmax/1000)
                mark_preds.append(confidence)
            else:  # negative VOT
                xmin_preds.append(xmin_proc_win[k] + xmax/1000)
                xmax_preds.append(xmin_proc_win[k] + xmin/1000)
                mark_preds.append("neg " + confidence)
                # print confidence, (xmin/1000), (xmax/1000), xmin_proc_win[k], " --> ", xmin_proc_win[k] + (xmin/1000), \
                #     xmin_proc_win[k] + (xmax/1000), " [", confidence, "]"
            k += 1

        # add "AutoVOT" tier to textgrid_filename
        textgrid = TextGrid()
        textgrid.read(textgrid_file)
        auto_vot_tier = IntervalTier(name='AutoVOT', xmin=textgrid.xmin(), xmax=textgrid.xmax())
        auto_vot_tier.append(Interval(textgrid.xmin(), xmin_preds[0], ''))
        # print textgrid.xmin(), xmin_preds[0], ''
        for i in xrange(len(xmin_preds) - 1):
            auto_vot_tier.append(Interval(xmin_preds[i], xmax_preds[i], mark_preds[i]))
            # print xmin_preds[i], xmax_preds[i], mark_preds[i]
            auto_vot_tier.append(Interval(xmax_preds[i], xmin_preds[i + 1], ''))
            # print xmax_preds[i], xmin_preds[i+1], ''
        auto_vot_tier.append(Interval(xmin_preds[-1], xmax_preds[-1], mark_preds[-1]))
        # print xmin_preds[-1], xmax_preds[-1], mark_preds[-1]
        auto_vot_tier.append(Interval(xmax_preds[-1], textgrid.xmax(), ''))
        # print xmax_preds[-1], textgrid.xmax(), ''

        ## check if target textgrid already has a tier named
        ## "AutoVOT", modulo preceding or trailing spaces or case. If
        ## so, action taken depends on if --ignore_existing_tiers flag
        ## invoked
        existing_tiers = [n.strip() for n in textgrid.tierNames(case="lower") if n.strip() == 'autovot']
        if len(existing_tiers) > 0:
            logging.warning("File %s already contains a tier with the name \"AutoVOT\"" % textgrid_file)
            if args.ignore_existing_tiers:
                logging.warning("Writing a new AutoVOT tier (in addition to existing one(s))")
                textgrid.append(auto_vot_tier)
                textgrid.write(textgrid_file)
            else:
                logging.warning("New \"AutoVOT\" tier is NOT being written to the file.")
                logging.warning("(use the --ignore_existing_tiers flag if you'd like to do so)")
        else:
            textgrid.append(auto_vot_tier)
            textgrid.write(textgrid_file)

        # delete the working directory at the end
        if args.logging_level != "DEBUG":
            shutil.rmtree(path=working_dir, ignore_errors=True)

    if len(problematic_files):
        logging.warning("**********************************")
        logging.warning("Prediction made for all files except these ones, where something was wrong:")
        logging.warning(problematic_files)
        logging.warning("Look for lines beginning with WARNING or ERROR in the program's output to see what went "
                        "wrong.")
        logging.warning("**********************************")

    logging.info("All done.")
