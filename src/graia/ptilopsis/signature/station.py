from typing import Dict, List, Optional, Tuple, TypeVar, Union

from graia.application.message.chain import MessageChain
from graia.application.message.elements.internal import Plain
from graia.ptilopsis.signature import FullMatch, NormalMatch, PatternReceiver, Require
from graia.ptilopsis.signature.pack import Arguments, merge_signature_chain
from graia.ptilopsis.utilles import InsertGenerator, merge_chain_plain, silce_chain_start

import re

T = Union[NormalMatch, PatternReceiver]
U = Union[T, List[T], Tuple[T]]

MessageIndex = Tuple[int, Optional[int]]

_T = TypeVar("_T")

def origin_or_zero(origin: Optional[_T]) -> Union[_T, int]:
    if origin is None:
        return 0
    return origin

class Station:
    def __init__(self) -> None:
        pass

    def match(self,
        signature_chain: Tuple[U],
        message_chain: MessageChain,
        matching_recevier: Optional[Arguments] = None
    ) -> Optional[Dict[str, MessageChain]]:
        merged_chain = merge_signature_chain(signature_chain)
        message_chain = merge_chain_plain(message_chain)
    
        reached_message_index: MessageIndex = (0, None)
        # [0] => real_index
        # [1] => text_index(optional)

        start_index: MessageIndex = (0, None)

        match_result: Dict[Arguments, Tuple[
            MessageIndex, # start(include)
            MessageIndex  # stop(exclude)
        ]] = {}
        
        signature_iterable = InsertGenerator(enumerate(merged_chain))

        for signature_index, signature in signature_iterable:
            if isinstance(signature, Arguments):
                if matching_recevier: # 已经选中了一个...
                    raise TypeError("a unexpected case: match conflict")
                matching_recevier = signature
                start_index = reached_message_index
            elif isinstance(signature, PatternReceiver):
                if not matching_recevier:
                    # 如果不要求匹配参数, 从当前位置(reached_message_index)开始匹配FullMatch.
                    current_chain = silce_chain_start(message_chain, reached_message_index)
                    if not current_chain.__root__: # index 越界
                        return
                    if not isinstance(current_chain.__root__[0], Plain):
                        # 切片后第一个**不是** Plain.
                        return
                    match_result = re.match(signature.operator(), current_chain.__root__[0].text)
                    if not match_result:
                        # 不匹配的
                        return
                    # 推进当前进度.
                    plain_text_length = len(current_chain.__root__[0].text)
                    pattern_length = match_result.end() - match_result.start()
                    if (pattern_length + 1) >= plain_text_length:
                        # 不推进 text_index 进度, 转而推进 element_index 进度(大概率是真正的全匹配.).
                        reached_message_index = (reached_message_index[0] + 1, None)
                    else:
                        # 推进 element_index 进度至已匹配到的地方后.
                        reached_message_index = (reached_message_index[0], origin_or_zero(reached_message_index[1]) + pattern_length)
                else:
                    # 需要匹配参数(是否贪婪模式查找, 即是否从后向前)
                    greed = matching_recevier.isGreed
                    for element_index, element in \
                        enumerate(silce_chain_start(message_chain, reached_message_index).__root__):
                        if isinstance(element, Plain):
                            current_text: str = element.text
                            # 在这行完成贪婪判断!
                            text_find_result = list(re.finditer(signature.operator(), current_text))[
                                -int(greed)
                                # -0 = 0
                                # -1 = -1
                            ]
                            text_find_index = text_find_result.start()

                            if text_find_index != -1:
                                # 找到了! 这里不仅要推进进度, 还要把当前匹配的参数记录结束位置并清理.
                                stop_index = (reached_message_index[0] + element_index + 1, text_find_index)
                                match_result[matching_recevier] = (start_index, stop_index)
                                start_index = reached_message_index
                                matching_recevier = None
                                pattern_length = text_find_result.end() - text_find_result.start()
                                if text_find_index + pattern_length >= len(current_text):
                                    # 此处是如果推进 text_index 就会被爆破....
                                    # 推进 element_index 而不是 text_index
                                    reached_message_index = (reached_message_index[0] + 1, None)
                                else:
                                    reached_message_index = (
                                        reached_message_index[0] + element_index,
                                        origin_or_zero(reached_message_index[1]) + text_find_index + pattern_length
                                    )
                                break
                    else:
                        # 找遍了都没匹配到.
                        return
            elif isinstance(signature, list):
                for sub_signature in signature:
                    if not isinstance(sub_signature, (tuple, list)):
                        sub_signature = [sub_signature]
                    sub_match_signature = [*sub_signature, *merged_chain[signature_index + 1:]]
                    result = self.match(
                        sub_match_signature,
                        silce_chain_start(message_chain, reached_message_index), # 因为推进都是推进到后面, 是安全的操作.
                        matching_recevier
                    )
                    if result:
                        return {
                            *match_result,
                            *result
                        }
                else:
                    # 整个元素都没匹配到.
                    return
            elif isinstance(signature, tuple):
                # 保留当前 signature_index 防止处理并列时发生错误.
                signature_iterable.insert_items.append(
                    (signature_index, i for i in signature)
                )
        else:
            if matching_recevier: # 到达了终点, 却仍然还要做点事的.
                # 计算终点坐标.
                text_index = None

                latest_element = message_chain.__root__[-1]
                if isinstance(latest_element, Plain):
                    text_index = len(latest_element.text)

                stop_index = (len(message_chain.__root__), text_index)
                match_result[matching_recevier] = (start_index, stop_index)
        return match_result

if __name__ == "__main__":
    from graia.ptilopsis.signature import Require
    from graia.ptilopsis.utilles import silce_chain_stop
    from devtools import debug
    from graia.application.entry import At
    # 这里是测试代码
    test_message_chain = MessageChain.create([
        Plain("test_matchre_test_argumentafterafter23123312323123231232323"), At(123)
    ])
    test_signature_chain = (
        FullMatch("test_match"),
        Require(name="require_1", isGreed=True),
        (FullMatch("after"),
        Require(name="require_2"))
    )
    test_station = Station(test_signature_chain)
    match_result = test_station.match(test_message_chain)
    debug(match_result)
    debug({k: silce_chain_stop(silce_chain_start(test_message_chain, v[0]), v[1]) for k, v in match_result.items()})
