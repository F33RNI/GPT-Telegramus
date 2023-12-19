import doctest
import BotHandler
import unittest

def load_tests(loader, tests, ignore):
    tests.addTests(doctest.DocTestSuite(BotHandler))
    return tests