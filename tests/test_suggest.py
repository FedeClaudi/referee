from refy import suggest, suggest_one
from refy.settings import example_path, base_dir
import pandas as pd


def test_suggst_one():
    suggest_one("neuron gene expression brain nervous system", N=20)

    suggestions = suggest_one(
        "neuron gene expression brain nervous system",
        N=20,
        since=2015,
        to=2018,
    )

    assert suggestions.suggestions.suggestions.year.min() == 2015
    assert suggestions.suggestions.suggestions.year.max() == 2018


def test_suggest_save():
    # create a path to save the suggestions to
    save_path = base_dir / "ref_test.csv"
    if save_path.exists():
        save_path.unlink()

    # get suggestions
    suggestions = suggest(example_path, N=20, savepath=save_path).suggestions

    # check suggestions
    assert len(suggestions) == 20, "wrong number of sugg"

    # check saved suggestions
    assert save_path.exists(), "didnt save"
    saved = pd.read_csv(save_path)

    assert len(saved) == 20, "loaded has wrong length"

    save_path.unlink()


def test_suggest_criteria():

    # test criteria
    suggestions = suggest(example_path, N=20, since=2015, to=2019).suggestions

    assert suggestions.suggestions.year.min() == 2015, "since doesnt work"
    assert suggestions.suggestions.year.max() == 2019, "to doesnt work"
