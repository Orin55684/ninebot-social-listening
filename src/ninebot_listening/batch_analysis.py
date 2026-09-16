"""Independent feedback classification in small batches; strict identity validation."""
import json
from . import contextual,replay
from .models import ModelRequest,DataClassification


def request(gateway, contexts):
    enums=json.dumps({'topic':replay.TOPICS,'issue':contextual.ISSUES,'intent':contextual.INTENTS,'level':['R1','R2','R3','R4']},ensure_ascii=False)
    response=gateway.analyze_json(ModelRequest(
        system_prompt=contextual.prompt(replay.TOPICS)+'\n本次输入items包含多条相互独立的反馈，绝不能互相作为上下文。逐条按以上规则判断。输出JSON对象{"results":[...]}，每项保留输入target.id为id，另包含上述全部分类字段。每个输入id恰好输出一次，不得遗漏、重复或加入未知id。\n字段枚举再次明确：'+enums+'。topic为宽泛主题，issue为具体问题，两者不能混用，例如充电异常只能作为issue，topic应选电池续航。无法匹配时topic选其他、issue选其他或无法判断。safety_claim必须是JSON布尔值true或false。',
        user_prompt=json.dumps({'items':contexts},ensure_ascii=False),
        data_classification=DataClassification.COMPANY_APPROVED,max_tokens=500*len(contexts)))
    results=response.payload.get('results')
    if not isinstance(results,list):raise ValueError('missing batch results')
    expected={x['target']['id'] for x in contexts}
    if len(results)!=len(expected) or any(not isinstance(x,dict) or not isinstance(x.get('id'),str) for x in results):raise ValueError('invalid batch identities')
    if {x['id'] for x in results}!=expected:raise ValueError('batch identity mismatch')
    for result in results:contextual.validate(result,replay.TOPICS)
    return response, {x['id']:x for x in results}


def save(c,context,result,model):
    d=result;level=contextual.validate(d,replay.TOPICS);reason=replay.scrub(d['reason'])[:200]
    if level!=d['level']:reason+='；系统校验调整等级：咨询/否认等不升级，R1必须有明确安全反馈依据。'
    c.execute('''INSERT OR REPLACE INTO analysis
      (message_id,topic,level,summary,confidence,status,error,model,issue,vehicle,intent,reason,model_level,version,context_json)
      VALUES (?,?,?,?,?,?,?,?,?,?,?,?,?,?,?)''',
      (context['target']['id'],d['topic'],level,replay.scrub(d['summary'])[:200],d['confidence'],'ok',None,model,d['issue'],replay.scrub(d['vehicle']).upper(),d['intent'],reason,d['level'],contextual.VERSION,json.dumps(context,ensure_ascii=False)))
    c.commit()
