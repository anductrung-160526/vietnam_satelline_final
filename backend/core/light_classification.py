"""Phân lớp cường độ bức xạ VIIRS kế thừa tài liệu; độc lập ngưỡng pixel sáng."""
SCHEME = 'ozturk_2025_fixed_v1'
BREAKS = [0.5, 2.0, 10.0, 20.0]
METHOD_VERSION = 'viirs_brightness_classes_v4_literature_fractional'
NAMES = ['Thấp nhất', 'Rất thấp', 'Thấp', 'Trung bình', 'Cao']
SOURCES = [
    {'title': 'Ozturk & Ozturk (2025), Bảng 3, trang 72', 'url': 'https://doi.org/10.3986/AGS.14506'},
    {'title': 'Widmer và cộng sự (2022), ETC-HE 2022/8, Bảng 4.2',
     'url': 'https://www.eionet.europa.eu/etcs/etc-he/products/etc-he-products/etc-he-report-2022-8-review-and-assessment-of-available-information-on-light-pollution-in-europe'},
]


def configuration():
    return dict(scheme=SCHEME, breaks=list(BREAKS), unit='nW/cm²/sr',
                classes=[dict(class_index=i, name=name, lower_bound=0 if i==0 else BREAKS[i-1],
                              upper_bound=BREAKS[i] if i<4 else None) for i,name in enumerate(NAMES)],
                sources=SOURCES,
                interpretation='Phân lớp cường độ bức xạ kế thừa tài liệu; chưa phải các mức phát triển kinh tế đã được kiểm chứng cho Việt Nam.')


def matches_current(classes, summary):
    if len(classes)!=5 or not summary or summary.get('method_version')!=METHOD_VERSION:
        return False
    return all(actual.get('class_index')==expected['class_index']
               and actual.get('lower_bound')==expected['lower_bound']
               and actual.get('upper_bound')==expected['upper_bound']
               for actual,expected in zip(classes,configuration()['classes']))
