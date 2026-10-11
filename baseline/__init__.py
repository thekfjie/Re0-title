from engine.text import JapaneseAnalyzer
from engine.layout import LayoutEngine,load_config
from engine.conversion import convert_kanji

def generate(text,fonts,**options):
    input_mode=options.pop('input_mode','kanji')
    if input_mode not in ('kanji','original'):raise ValueError('无模型入口只支持汉字字形转换或保留原文；中文整句翻译是独立模型服务')
    preprocessing=convert_kanji(text) if input_mode=='kanji' else {'source_text':text,'text':text,'changed':False,'method':'original'}
    text=preprocessing['text']
    config=load_config();tokens=JapaneseAnalyzer(config['rules']).analyze(text,options.pop('heuristic',None))
    results=LayoutEngine(fonts,config).generate(text,tokens,**options)
    for l in results:l.metadata['preprocessing']=preprocessing
    return results
