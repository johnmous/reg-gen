###################################################################################################
# Libraries
###################################################################################################

# Python
from __future__ import print_function
import numpy as np
import math
from sklearn import metrics
from scipy.integrate import trapz
import matplotlib
matplotlib.use('Agg')
import matplotlib.pyplot as plt
import pylab

from pysam import Samfile

# Internal
from rgt.GenomicRegionSet import GenomicRegionSet
from rgt.Util import OverlapType
from ..Util import GenomeData

"""
Evaluate the footprints prediction using TF ChIP-seq or expression data.

Authors: Eduardo G. Gusmao, Zhijian Li
"""


class Evaluation:
    """
    Contains two different methodologies: TF ChIP-seq Based Evaluation

    """

    def __init__(self, tf_name, tfbs_file, footprint_file, footprint_name, footprint_type,
                 print_roc_curve, print_pr_curve, output_location, alignment_file, organism):
        self.tf_name = tf_name
        self.tfbs_file = tfbs_file
        self.footprint_file = footprint_file.split(",")
        self.footprint_name = footprint_name.split(",")
        self.footprint_type = footprint_type.split(",")
        self.print_roc_curve = print_roc_curve
        self.print_pr_curve = print_pr_curve
        self.output_location = output_location
        self.alignment_file = alignment_file
        self.organism = organism
        if self.output_location[-1] != "/":
            self.output_location += "/"

    def chip_evaluate(self):
        """
        This evaluation methodology uses motif-predicted binding sites (MPBSs) together with TF ChIP-seq data
        to evaluate the footprint predictions.

        return:
        """

        # Evaluate Statistics
        fpr = dict()
        tpr = dict()
        roc_auc = dict()
        roc_auc_1 = dict()
        roc_auc_2 = dict()
        recall = dict()
        precision = dict()
        prc_auc = dict()

        if "SEG" in self.footprint_type:
            mpbs_regions = GenomicRegionSet("TFBS")
            mpbs_regions.read_bed(self.tfbs_file)
            mpbs_regions.sort()

            # Verifying the maximum score of the MPBS file
            max_score = -99999999
            for region in iter(mpbs_regions):
                score = int(region.data)
                if score > max_score:
                    max_score = score
            max_score += 1

        for i in range(len(self.footprint_file)):
            footprints_regions = GenomicRegionSet("Footprints Prediction")
            footprints_regions.read_bed(self.footprint_file[i])

            # Sort footprint prediction bed files
            footprints_regions.sort()

            if self.footprint_type[i] == "SEG":
                # Increasing the score of MPBS entry once if any overlaps found in the predicted footprints.
                increased_score_mpbs_regions = GenomicRegionSet("Increased Regions")
                intersect_regions = mpbs_regions.intersect(footprints_regions, mode=OverlapType.ORIGINAL)
                for region in iter(intersect_regions):
                    region.data = str(int(region.data) + max_score)
                    increased_score_mpbs_regions.add(region)


                # Keep the score of remained MPBS entry unchanged
                without_intersect_regions = mpbs_regions.subtract(footprints_regions, whole_region=True)
                for region in iter(without_intersect_regions):
                    increased_score_mpbs_regions.add(region)

                increased_score_mpbs_regions.sort_score()

                fpr[i], tpr[i], roc_auc[i], roc_auc_1[i], roc_auc_2[i] = self.roc_curve(increased_score_mpbs_regions)
                recall[i], precision[i], prc_auc[i] = self.precision_recall_curve(increased_score_mpbs_regions)
            elif self.footprint_type[i] == "SC":
                footprints_regions.sort_score()
                fpr[i], tpr[i], roc_auc[i], roc_auc_1[i], roc_auc_2[i] = self.roc_curve(footprints_regions)
                recall[i], precision[i], prc_auc[i] = self.precision_recall_curve(footprints_regions)

        # Output the statistics results into text
        stats_fname = self.output_location + self.tf_name + "_stats.txt"
        stats_header = ["METHOD", "AUC_100", "AUC_10", "AUC_1", "AUPR"]
        with open(stats_fname, "w") as stats_file:
            stats_file.write("\t".join(stats_header) + "\n")
            for i in range(len(self.footprint_name)):
                stats_file.write(self.footprint_name[i] + "\t" + str(roc_auc[i]) + "\t" + str(roc_auc_1[i]) + "\t"
                                 + str(roc_auc_2[i]) + "\t" + str(prc_auc[i]) + "\n")

        # Output the curves
        if self.print_roc_curve:
            label_x = "False Positive Rate"
            label_y = "True Positive Rate"
            curve_name = "ROC"
            self.plot_curve(fpr, tpr, roc_auc, label_x, label_y, self.tf_name, curve_name)
        if self.print_pr_curve:
            label_x = "Recall"
            label_y = "Precision"
            curve_name = "PRC"
            self.plot_curve(recall, precision, prc_auc, label_x, label_y, self.tf_name, curve_name)

        self.output_points(self.tf_name, fpr, tpr, recall, precision)

    def plot_curve(self, data_x, data_y, stats, label_x, label_y, tf_name, curve_name):
        color_list = ["#000000", "#000099", "#006600", "#990000", "#660099", "#CC00CC", "#222222", "#CC9900",
                      "#FF6600", "#0000CC", "#336633", "#CC0000", "#6600CC", "#FF00FF", "#555555", "#CCCC00",
                      "#FF9900", "#0000FF", "#33CC33", "#FF0000", "#663399", "#FF33FF", "#888888", "#FFCC00",
                      "#663300", "#009999", "#66CC66", "#FF3333", "#9933FF", "#FF66FF", "#AAAAAA", "#FFCC33",
                      "#993300", "#00FFFF", "#99FF33", "#FF6666", "#CC99FF", "#FF99FF", "#CCCCCC", "#FFFF00"]

        matplotlib.use('Agg')
        # Creating figure
        fig = plt.figure(figsize=(8, 5), facecolor='w', edgecolor='k')
        ax = fig.add_subplot(111)
        for i in range(len(self.footprint_name)):
            ax.plot(data_x[i], data_y[i], color=color_list[i],
                    label=self.footprint_name[i] + ": " + str(round(stats[i], 4)))

        # Plot red diagonal line
        ax.plot([0, 1.0], [0, 1.0], color="#CCCCCC", linestyle="--", alpha=1.0)

        # Line legend
        leg = ax.legend(bbox_to_anchor=(1.0, 0.0, 1.0, 1.0), loc=2, ncol=2, borderaxespad=0., title="AUC",
                        prop={'size': 4})
        for e in leg.legendHandles:
            e.set_linewidth(2.0)

        # Titles and Axis Labels
        ax.set_title(tf_name)
        ax.set_xlabel(label_x)
        ax.set_ylabel(label_y)

        # Ticks
        ax.grid(True, which='both')
        ax.set_xticks(np.arange(0.0, 1.01, 0.1))
        ax.set_yticks(np.arange(0.0, 1.01, 0.1))
        for tick in ax.xaxis.get_major_ticks():
            tick.label.set_fontsize(10)
        for tick in ax.yaxis.get_major_ticks():
            tick.label.set_fontsize(10)

        # Axis limits
        pylab.xlim([0, 1.0])
        pylab.ylim([0, 1.0])

        # Saving figure
        figure_name = self.output_location + tf_name + "_" + curve_name + ".png"
        fig.savefig(figure_name, format="png", dpi=300, bbox_inches='tight', bbox_extra_artists=[leg])

    def roc_curve(self, sort_score_regions):
        count_x = 0
        count_y = 0
        fpr = [count_x]
        tpr = [count_y]
        for region in iter(sort_score_regions):
            if str(region.name).split(":")[-1] == "Y":
                count_y += 1
                fpr.append(count_x)
                tpr.append(count_y)
            else:
                count_x += 1
                fpr.append(count_x)
                tpr.append(count_y)
        fpr = [e * (1.0 / count_x) for e in fpr]
        tpr = [e * (1.0 / count_y) for e in tpr]

        # Evaluating 100% AUC
        roc_auc = metrics.auc(fpr, tpr)

        # Evaluating 10% AUC
        fpr_auc = 0.1
        fpr_1 = list()
        tpr_1 = list()
        for idx in range(0, len(fpr)):
            if (fpr[idx] > fpr_auc): break
            fpr_1.append(fpr[idx])
            tpr_1.append(tpr[idx])
        roc_auc_1 = metrics.auc(self.standardize(fpr_1), tpr_1)

        # Evaluating 1% AUC
        fpr_auc = 0.01
        fpr_2 = list()
        tpr_2 = list()
        for idx in range(0, len(fpr)):
            if (fpr[idx] > fpr_auc):
                break
            fpr_2.append(fpr[idx])
            tpr_2.append(tpr[idx])
        roc_auc_2 = metrics.auc(self.standardize(fpr_2), tpr_2)

        return fpr, tpr, roc_auc, roc_auc_1, roc_auc_2

    def precision_recall_curve(self, sort_score_regions):
        count_x = 0
        count_y = 0
        precision = [0.0]
        recall = [0.0]
        for region in iter(sort_score_regions):
            if str(region.name).split(":")[-1] == "Y":
                count_y += 1
                precision.append(float(count_y) / (count_x + count_y))
                recall.append(count_y)
            else:
                count_x += 1
                precision.append(float(count_y) / (count_x + count_y))
                recall.append(count_y)

        recall = [e * (1.0 / count_y) for e in recall]
        precision.append(0.0)
        recall.append(1.0)
        auc = (abs(trapz(recall, precision)))

        return recall, precision, auc

    def standardize(self, vector):
        maxN = max(vector)
        minN = min(vector)
        return [(e - minN) / (maxN - minN) for e in vector]

    def optimize_roc_points(self, fpr, tpr, max_points=1000):
        new_fpr = dict()
        new_tpr = dict()
        for i in range(len(self.footprint_name)):
            if (len(fpr[i]) > max_points):
                new_idx_list = [int(math.ceil(e)) for e in np.linspace(0, len(fpr[i]) - 1, max_points)]
                new_idx_fpr = []
                new_idx_tpr = []
                for j in new_idx_list:
                    new_idx_fpr.append(fpr[i][j])
                    new_idx_tpr.append(tpr[i][j])
                new_fpr[i] = new_idx_fpr
                new_tpr[i] = new_idx_tpr
            else:
                new_fpr[i] = fpr[i]
                new_tpr[i] = tpr[i]

        return new_fpr, new_tpr

    def optimize_pr_points(self, recall, precision, max_points=1000):
        new_recall = dict()
        new_precision = dict()

        for i in range(len(self.footprint_name)):
            data_recall = []
            data_precision = []
            for j in range(min(max_points, len(recall[i]))):
                data_recall.append(recall[i].pop(0))
                data_precision.append(precision[i].pop(0))
            if len(recall[i]) > max_points:
                new_idx_list = [int(math.ceil(e)) for e in np.linspace(0, len(recall[i]) - 1, max_points)]
                for j in new_idx_list:
                    data_recall.append(recall[i][j])
                    data_precision.append(precision[i][j])
                new_recall[i] = data_recall
                new_precision[i] = data_precision
            else:
                new_recall[i] = data_recall + recall[i]
                new_precision[i] = data_precision + precision[i]

        return new_recall, new_precision

    def output_points(self, tf_name, fpr, tpr, recall, precision):
        roc_fname = self.output_location + tf_name + "_roc.txt"
        new_fpr, new_tpr = self.optimize_roc_points(fpr, tpr)
        header = list()
        len_vec = list()
        for i in range(len(self.footprint_name)):
            header.append(self.footprint_name[i] + "_FPR")
            header.append(self.footprint_name[i] + "_TPR")
            len_vec.append(len(new_fpr[i]))

        with open(roc_fname, "w") as roc_file:
            roc_file.write("\t".join(header) + "\n")
            max_idx = len_vec.index(max(len_vec))
            for j in range(len(new_fpr[max_idx])):
                to_write = list()
                for i in range(len(self.footprint_name)):
                    if j >= len(new_fpr[i]):
                        to_write.append("NA")
                    else:
                        to_write.append(str(new_fpr[i][j]))
                    if j >= len(new_tpr[i]):
                        to_write.append("NA")
                    else:
                        to_write.append(str(new_tpr[i][j]))
                roc_file.write("\t".join(to_write) + "\n")

        prc_fname = self.output_location + tf_name + "_prc.txt"
        new_recall, new_precision = self.optimize_pr_points(recall, precision)
        header = list()
        len_vec = list()
        for i in range(len(self.footprint_name)):
            header.append(self.footprint_name[i] + "_REC")
            header.append(self.footprint_name[i] + "_PRE")
            len_vec.append(len(new_recall[i]))

        with open(prc_fname, "w") as prc_file:
            prc_file.write("\t".join(header) + "\n")
            max_idx = len_vec.index(max(len_vec))
            for j in range(len(new_recall[max_idx])):
                to_write = list()
                for i in range(len(self.footprint_name)):
                    if j >= len(new_recall[i]):
                        to_write.append("NA")
                    else:
                        to_write.append(str(new_recall[i][j]))
                    if j >= len(new_precision[i]):
                        to_write.append("NA")
                    else:
                        to_write.append(str(new_precision[i][j]))
                prc_file.write("\t".join(to_write) + "\n")
