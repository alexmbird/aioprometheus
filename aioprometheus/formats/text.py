''' This module implements a Prometheus metrics text formatter '''

import collections

from .base import IFormatter
from ..collectors import Counter, Gauge, Summary, Histogram


HELP_FMT = "# HELP {name} {doc}"
TYPE_FMT = "# TYPE {name} {kind}"
COMMENT_FMT = "# {comment}"
LABEL_FMT = "{key}=\"{value}\""
LABEL_SEPARATOR_FMT = ","
LINE_SEPARATOR_FMT = "\n"
METRIC_FMT = "{name}{labels} {value} {timestamp}"
POS_INF = float("inf")
NEG_INF = float("-inf")


class TextFormatter(IFormatter):
    ''' This formatter encodes into the Protocol Buffers binary format '''

    def __init__(self, timestamp=False):
        """timestamp is a boolean, if you want timestamp in each metric"""
        self.timestamp = timestamp
        self._headers = {
            'Content-Type': 'text/plain; version=0.0.4; charset=utf-8'}

    def get_headers(self):
        return self._headers

    def _format_line(self, name, labels, value, const_labels=None):
        labels_str = ""
        ts = ""

        labels = self._unify_labels(labels, const_labels, True)

        if labels:
            labels_str = [
                LABEL_FMT.format(key=k, value=v)
                for k, v in labels.items()]
            labels_str = LABEL_SEPARATOR_FMT.join(labels_str)
            labels_str = "{{{labels}}}".format(labels=labels_str)

        if self.timestamp:
            ts = self._get_timestamp()

        result = METRIC_FMT.format(
            name=name, labels=labels_str, value=value, timestamp=ts)

        return result.strip()

    def _format_counter(self, counter, name, const_labels):
        '''
        :param counter: a 2-tuple containing labels and the counter value.
        :param labels: a dict of labels for a metric.
        :param const_labels: a dict of constant labels to be associated with
          the metric.
        '''
        labels, value = counter
        return self._format_line(name, labels, value, const_labels)

    def _format_gauge(self, gauge, name, const_labels):
        '''
        :param gauge: a 2-tuple containing labels and the gauge value.
        :param labels: a dict of labels for a metric.
        :param const_labels: a dict of constant labels to be associated with
          the metric.
        '''
        labels, value = gauge
        return self._format_line(name, labels, value, const_labels)

    def _format_summary(self, summary, name, const_labels):
        '''
        :param summary: a 2-tuple containing labels and a dict representing
          the summary value. The dict contains keys for each quantile as
          well as the sum and count fields.
        :param labels: a dict of labels for a metric.
        :param const_labels: a dict of constant labels to be associated with
          the metric.
        '''
        summary_labels, summary_value_dict = summary
        results = []

        for k, v in summary_value_dict.items():
            # Start from a fresh dict for the labels (new or with preset data)
            if summary_labels:
                labels = summary_labels.copy()
            else:
                labels = {}

            # Quantiles need labels and not special name (like sum and count)
            if type(k) is not float:
                name_str = "{0}_{1}".format(name, k)
            else:
                labels['quantile'] = k
                name_str = name
            results.append(
                self._format_line(name_str, labels, v, const_labels))

        return results

    def _format_histogram(self, histogram, name, const_labels):
        '''
        :param histogram: a 2-tuple containing labels and a dict representing
          the histogram value. The dict contains keys for each bucket as
          well as the sum and count fields.
        :param labels: a dict of labels for a metric.
        :param const_labels: a dict of constant labels to be associated with
          the metric.
        '''
        histogram_labels, histogram_value_dict = histogram
        results = []

        for k, v in histogram_value_dict.items():
            # Stat from a fresh dict for the labels (new or with preset data)
            if histogram_labels:
                labels = histogram_labels.copy()
            else:
                labels = {}

            # Buckets need labels and not special name (like sum and count)
            if type(k) is not float:
                name_str = "{0}_{1}".format(name, k)
            else:
                upper_bound = k
                if upper_bound == POS_INF:
                    upper_bound = '+Inf'
                elif upper_bound == NEG_INF:
                    upper_bound = '-Inf'
                # Add the le ("less or equal") label.
                labels['le'] = upper_bound
                # Use the special bucket label name
                name_str = name + '_bucket'
            results.append(
                self._format_line(name_str, labels, v, const_labels))

        return results

    def marshall_lines(self, collector):
        '''
        Marshalls a collector and returns the storage/transfer format in
        a tuple, this tuple has reprensentation format per element.
        '''
        if isinstance(collector, Counter):
            exec_method = self._format_counter
        elif isinstance(collector, Gauge):
            exec_method = self._format_gauge
        elif isinstance(collector, Summary):
            exec_method = self._format_summary
        elif isinstance(collector, Histogram):
            exec_method = self._format_histogram
        else:
            raise TypeError("Not a valid object format")

        # create headers
        help_header = HELP_FMT.format(
            name=collector.name, doc=collector.doc)

        type_header = TYPE_FMT.format(
            name=collector.name, kind=collector.kind.name)

        # Prepare start headers
        lines = [help_header, type_header]

        for i in collector.get_all():
            r = exec_method(i, collector.name, collector.const_labels)

            # Check if it returns one or multiple lines
            if not isinstance(r, str) and isinstance(r, collections.Iterable):
                lines.extend(r)
            else:
                lines.append(r)

        return lines

    def marshall_collector(self, collector):
        # need sort?
        result = sorted(self.marshall_lines(collector))
        return LINE_SEPARATOR_FMT.join(result)

    def marshall(self, registry):
        ''' Marshalls a full registry (various collectors) into a bytes
        object '''

        blocks = []
        for i in registry.get_all():
            blocks.append(self.marshall_collector(i))

        # Sort? used in tests
        blocks = sorted(blocks)

        # Needs EOF
        blocks.append("")

        return LINE_SEPARATOR_FMT.join(blocks).encode('utf-8')