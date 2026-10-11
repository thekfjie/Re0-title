from engine.text import JapaneseAnalyzer
from engine.layout import LayoutEngine,load_config

def generate(text,fonts,**options):
    config=load_config();tokens=JapaneseAnalyzer(config['rules']).analyze(text,options.pop('heuristic',None))
    return LayoutEngine(fonts,config).generate(text,tokens,**options)
