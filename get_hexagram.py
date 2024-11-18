from flask import Flask, jsonify
import random

app = Flask(__name__)

def toss_a_coin(n=6):
    return ['阴' if random.random() < 0.5 else '阳' for _ in range(n)]

def judge_hexagram(results):
    map = {
        '111': '乾',
        '000': '坤',
        '101': '离',
        '010': '坎',
        '001': '震',
        '100': '艮',
        '110': '巽',
        '011': '兑'
    }

    def convert_to_binary_string(result):
        return ''.join(['1' if r == '阳' else '0' for r in result])

    upper_trigram = convert_to_binary_string(results[:3])  # 修改：前三爻为上卦
    lower_trigram = convert_to_binary_string(results[3:])  # 修改：后三爻为下卦

    upper_name = map.get(upper_trigram, '未知')  # 修改：交换上下卦名称
    lower_name = map.get(lower_trigram, '未知')

    return f'上{upper_name}下{lower_name}'

@app.route('/api/getHexagram', methods=['GET'])
def get_hexagram():
    results = toss_a_coin()
    hexagram_name = judge_hexagram(results)
    return jsonify({'results': results, 'hexagramName': hexagram_name})

if __name__ == '__main__':
    app.run(debug=True)
