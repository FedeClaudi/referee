from loguru import logger
from rich import print
import sys
from pathlib import Path
from rich.spinner import Spinner
from rich.text import Text
from rich.live import Live

from pyinspect.panels import Report
from myterial import orange, salmon, orange_dark

sys.path.append("./")
from refy.input import load_user_input
from refy.database import load_database
from refy.progress import suggest_progress
from refy import doc2vec as d2v
from refy import download
from refy.suggestions import Suggestions
from refy.keywords import Keywords, get_keywords_from_text
from refy.authors import Authors
from refy.utils import get_authors, isin


class SimpleQuery:
    """
        Handles printing of simple queryies(i.e. not from .bib files) results
    """

    def __init__(self):
        download.check_files()

    def fill(self, papers, N, since, to):
        """
            Given a dataframe of papers and some arguments creates and 
            stores an instance of Suggestions and Authors

            Arguments:
                papers: pd. DataFrame of recomended papers
                N: int. Number of papers to suggest
                since: int or None. If an int is passed it must be a year,
                    only papers more recent than the given year are kept for recomendation
                to: int or None. If an int is passed it must be a year,
                    only papers older than that are kept for recomendation
        """
        # create suggestions
        self.suggestions = Suggestions(papers)
        self.suggestions.filter(since=since, to=to)
        self.suggestions.truncate(N)

        # get authors
        self.authors = Authors(self.suggestions.get_authors())

    def start(self, text):
        """ starts a spinner """
        self.live = Live(
            Spinner("bouncingBall", text=Text(text, style=orange))
        )

        self.live.start()

    def stop(self):
        """ stops a spinner """
        self.live.stop()

    def print(self, text_title=None, text=None, sugg_title=""):
        """
            Print a summary with some text, suggested papers and authors

            Arguments:
                text_title: str, title for text section
                text: str, text to place in the initial segment of the report
                sugg_title: str, title for the suggestions table
        """
        # print summary
        summary = Report(dim=orange)
        summary.width = 160

        # text
        if text is not None:
            if text_title is not None:
                summary.add(text_title)
            summary.add(text)

        # suggestions
        if sugg_title:
            summary.add(sugg_title)
        summary.add(
            self.suggestions.to_table(), "rich",
        )
        summary.spacer()
        summary.line(orange_dark)
        summary.spacer()

        # authors
        if len(self.authors):
            summary.add(f"[bold {salmon}]:lab_coat:  [u]top authors\n")
            summary.add(self.authors.to_table(), "rich")

        print(summary)
        print("")


class by_author(SimpleQuery):
    def __init__(self, *authors, N=20, since=None, to=None, savepath=None):
        """
            Print all authors in the database from a list of authors

            Arguments:
                authors: variable number of str with author names
                N: int. Number of papers to suggest
                since: int or None. If an int is passed it must be a year,
                    only papers more recent than the given year are kept for recomendation
                to: int or None. If an int is passed it must be a year,
                    only papers older than that are kept for recomendation
                savepath: str, Path. Path pointing to a .csv file where the recomendations
                    will be saved
        """

        def cleans(string):
            """ clean a single string """
            for pun in "!()-[]{};:,<>./?@#$%^&*_~":
                string = string.replace(pun, "")
            return string.lower()

        def clean(paper):
            """
                Clean the papers['authors_clean'] entry of the database
                by removing punctuation, forcing lower case etc.
            """
            return [cleans(a) for a in paper.authors_clean]

        SimpleQuery.__init__(self)
        self.start("extracting author's publications")

        logger.debug(
            f"Fining papers by author(s) with {len(authors)} author(s): {authors}"
        )

        # load and clean database
        papers = load_database()

        logger.debug("Cleaning up database author entries")
        papers["authors_clean"] = papers.apply(get_authors, axis=1)
        papers["authors_clean"] = papers.apply(clean, axis=1)

        # filter by author
        keep = papers["authors_clean"].apply(
            isin, args=[cleans(a) for a in authors]
        )
        papers = papers.loc[keep]
        logger.debug(f"Found {len(papers)} papers for authors")

        logger.debug(f"\n\nPapers matching authors:\n{papers.head()}\n\n")

        if papers.empty:
            print(
                f"[{salmon}]Could not find any papers for author(s): {authors}"
            )
            return

        # fill
        self.fill(papers, N, since, to)

        # print
        self.stop()
        ax = " ".join(authors)
        self.print(
            sugg_title=f'Suggestions for author(s): [bold {orange}]"{ax}"\n'
        )

        # save to file
        if savepath:
            self.suggestions.to_csv(savepath)


class suggest_one(SimpleQuery):
    def __init__(self, input_string, N=20, since=None, to=None, savepath=None):
        """
            Finds recomendations based on a single input string (with keywords,
            or a paper abstract or whatever) instead of an input .bib file

            Arguments:
                input_stirng: str. String to match against database
                N: int. Number of papers to suggest
                since: int or None. If an int is passed it must be a year,
                    only papers more recent than the given year are kept for recomendation
                to: int or None. If an int is passed it must be a year,
                    only papers older than that are kept for recomendation
                savepath: str, Path. Path pointing to a .csv file where the recomendations
                    will be saved

            Returns:
                suggestions: pd.DataFrame of N recomended papers
        """
        logger.debug("suggest one")
        SimpleQuery.__init__(self)
        self.start("Finding recomended papers")

        # load database and abstracts
        database = load_database()

        # load model
        model = d2v.D2V()

        # find recomendations
        best_IDs = model.predict(input_string, N=N)

        # fill
        papers = database.loc[database["id"].isin(best_IDs)]
        self.fill(papers, N, since, to)

        # print
        self.stop()
        self.print(
            text_title=f"[bold {salmon}]:mag:  [u]search keywords\n",
            text=input_string,
            sugg_title=f'Suggestions for input string: [bold {orange}]"{input_string}"',
        )

        # save to file
        if savepath:
            self.suggestions.to_csv(savepath)


class suggest:
    suggestions_per_paper = 100  # for each paper find N suggestions

    def __init__(self, user_papers, N=20, since=None, to=None, savepath=None):
        """
            Suggest new relevant papers based on the user's
            library.

            Arguments:
                user_papers: str, path. Path to a .bib file with user's papers info
                N: int. Number of papers to suggest
                since: int or None. If an int is passed it must be a year,
                    only papers more recent than the given year are kept for recomendation
                to: int or None. If an int is passed it must be a year,
                    only papers older than that are kept for recomendation
                savepath: str, Path. Path pointing to a .csv file where the recomendations
                    will be saved
        """
        download.check_files()

        self.since = since
        self.to = to
        if savepath:
            self.savepath = Path(savepath)
        else:
            self.savepath = savepath

        with suggest_progress as progress:
            self.progress = progress
            self.n_completed = -1
            self.task_id = self.progress.add_task(
                "Suggesting papers..", start=True, total=5, current_task="",
            )
            # load data
            self.load_data(user_papers)

            # load d2v model
            self._progress("Loading Doc2Vec model")
            self.d2v = d2v.D2V()

            # get keywords
            self._progress("Extracting keywords from data")
            self.get_keywords()

            # get suggestions
            self.get_suggestions(N=N)

    @property
    def n_papers(self):
        return len(self.database)

    @property
    def n_user_papers(self):
        return len(self.user_papers)

    def _progress(self, task_name):
        """
            Update progress bar
        """
        self.n_completed += 1
        self.progress.update(
            self.task_id, current_task=task_name, completed=self.n_completed
        )

    def load_data(self, user_papers):
        """
            Load papers metadata for user papers and database papers

            Arguments:
                user_papers: str, path. Path to a .bib file with user's papers info
        """
        # load database
        self._progress("Loading database papers")
        self.database = load_database()

        # load user data
        self._progress("Loading user papers",)
        self.user_papers = load_user_input(user_papers)

    def suggest_for_paper(self, user_paper_title, user_paper_abstract):
        """
            Finds the best matches for a single paper

            Arguments:
                user_paper_title: str. Title of input user paper
                user_paper_abstract: str. Abstract of input user paper

            Returns:
                suggestions: dict. Dictionary of title:value where value 
                    is self.suggestions_per_paper for the best match paper and 
                    1 for the lowest match
        """
        # find best match with d2v
        best_IDs = self.d2v.predict(
            user_paper_abstract, N=self.suggestions_per_paper
        )

        # get selected papers
        selected = self.database.loc[self.database["id"].isin(best_IDs)]

        if selected.empty:
            logger.debug(
                f'Could not find any suggested papers for paper: "{user_paper_title}" '
            )

        return {
            t: self.suggestions_per_paper - n
            for n, t in enumerate(selected.title.values)
        }

    def _collate_suggestions(self, points):
        """
            Given a dictionart of points for each suggested paper,
            this function returns a dataframe with papers ordered 
            by their score

            Arguments:
                points: dict of title:point entries for each recomended paper

            Returns
                suggestions: Suggestions with suggested papers ordred by score
        """
        # collate recomendations
        suggestions = Suggestions(
            self.database.loc[self.database.title.isin(points.keys())]
        )

        # drop suggestions whose title is in the user papers
        suggestions.remove_overlap(self.user_papers)

        # Get each paper's score
        max_score = self.suggestions_per_paper * self.n_user_papers
        score = [points[title] / max_score for title in suggestions.titles]
        suggestions.set_score(score)

        # keep only papers published within a given years range
        suggestions.filter(to=self.to, since=self.since)

        return suggestions

    def get_suggestions(self, N=20):
        """
            Finds the papers from the database that are not in the user's
            library but are most similar to the users papers.
            For each user paper, get the N most similar papers, then get
            the papers that came up most frequently across all user papers.
            

            Arguments:
                N: int, number of best papers to keep

            Returns:
                suggestions: Suggestions with suggested papers sorted by score
        """
        logger.debug(f"Getting suggestions for {self.n_user_papers} papers")

        # progress bar
        self._progress("Looking for good papers")
        select_task = self.progress.add_task(
            "Selecting the very best...",
            start=True,
            total=self.n_user_papers,
            current_task="analyzing...",
        )

        # find best matches for each paper
        points = {}
        for n, (idx, user_paper) in enumerate(self.user_papers.iterrows()):
            # keep track of recomendations across all user papers
            paper_suggestions = self.suggest_for_paper(
                user_paper.title, user_paper.abstract
            )

            for suggested, pts in paper_suggestions.items():
                if suggested in points.keys():
                    points[suggested] += pts
                else:
                    points[suggested] = pts

            self.progress.update(select_task, completed=n)
        self.progress.remove_task(select_task)
        self.progress.remove_task(self.task_id)

        # collate and print suggestions
        self.suggestions = self._collate_suggestions(points)
        self.suggestions.get_authors()

        self.suggestions.truncate(N)

        # save to file
        if self.savepath:
            self.suggestions.to_csv(self.savepath)

        # conclusion
        self.summarize()
        return self.suggestions

    def get_keywords(self):
        """
            Extracts set of keywords that best represent the user papers.
            These can be used to improve the search and to improve the
            print out from the query. 
        """
        task = self.progress.add_task(
            "Finding keywords...",
            start=True,
            total=self.n_user_papers,
            current_task="analyzing...",
        )

        keywords = {}
        for n, (idx, user_paper) in enumerate(self.user_papers.iterrows()):
            kwds = get_keywords_from_text(user_paper.abstract, N=10)

            for m, kw in enumerate(kwds):
                if kw in keywords.keys():
                    keywords[kw] += 10 - m
                else:
                    keywords[kw] = 1

            self.progress.update(task, completed=n)
        self.progress.remove_task(task)

        # sort keywords
        self.keywords = Keywords(keywords)

    def summarize(self):
        """
            Print results of query: keywords, recomended papers etc.
        """
        # create a list of most recomended authors
        authors = Authors(self.suggestions.authors)

        # get console with highlighter
        highlighter = self.keywords.get_highlighter()

        # create summary
        summary = Report(dim=orange)
        summary.width = 160

        # keywords
        summary.add(f"[bold {salmon}]:mag:  [u]keywords\n")
        summary.add(self.keywords.to_table(), "rich")
        summary.spacer()
        summary.line(orange_dark)
        summary.spacer()

        # suggestions
        summary.add(f"[bold {salmon}]:memo:  [u]recomended paper\n")
        summary.add(self.suggestions.to_table(highlighter=highlighter), "rich")
        summary.spacer()
        summary.line(orange_dark)
        summary.spacer()

        # authors
        summary.add(f"[bold {salmon}]:lab_coat:  [u]top authors\n")
        summary.add(authors.to_table(), "rich")
        summary.spacer()

        # print
        print(summary)
        print("")


if __name__ == "__main__":
    import refy

    refy.settings.TEST_MODE = True

    refy.set_logging("DEBUG")

    # suggest(refy.settings.example_path, N=25, since=2018)

    # suggest_one("locomotion control mouse steering goal directed")

    by_author("Gary  Stacey")
