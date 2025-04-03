from .base_fetcher import BaseFetcher
from .zol_fetcher import ZolFetcher
# 他のFetcherも実装したらここに追加する
# from .ithome_fetcher import IthomeFetcher
# from .cnmo_fetcher import CnmoFetcher
# from .pconline_fetcher import PconlineFetcher

# 利用可能なFetcherクラスを辞書などで管理しても良い
AVAILABLE_FETCHERS = {
    "zol": ZolFetcher,
    # "ithome": IthomeFetcher,
    # "cnmo": CnmoFetcher,
    # "pconline": PconlineFetcher,
}