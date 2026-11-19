# 鹭湾湿地观测湖

Python 3.11 标准库项目。监测站提交具名日批，归档员将两支探头的无符号原始计数和逐位 XOR 校验写到三个独立冷卷。夜班按固定地址领取，值班员从原序明细复算日账，档案员可以原位更正一个计数并凭原请求重领回执。

## 运行

- 完整回归 `python3 -B check_project.py`
- 交班演示 `python3 -B -m samples.demo`
- 单独核验半写期间的缺读 `python3 -B -m unittest tests.test_amendment.AmendmentTests.test_half_write`

演示使用独立临时目录。样例 L01 依序包含 R20 `(0,7)` 和 R03 `(5,9)`。R03 首值更正为 6，单行贡献由 14 到 15，完整日账由 21 到 22。

## 使用归档

```python
from pathlib import Path

from lake.archive import Archive
from lake.batch.intake import make_batch_input
from lake.batch.seal import seal_batch
from lake.read.collect import read_stripe
from lake.amend.requests import CorrectionRequest
from lake.amend.apply import apply_correction
from lake.amend.receipts import get_receipt
from lake.audit.selection import audit_batch
from lake.audit.reconcile import reconcile_correction
from lake.volume.layout import SlotRole

archive = Archive.initialize(Path('cold-archive'), bits=8)
sealed = seal_batch(archive, make_batch_input('L01', [('R20', 0, 7), ('R03', 5, 9)]))
address = sealed.members[1].address
original = read_stripe(archive, address)
before = audit_batch(archive, 'L01')
request = CorrectionRequest('C01', address, SlotRole.FIRST, 6)
receipt = apply_correction(archive, request)
assert get_receipt(archive, 'C01') == receipt
after = audit_batch(archive, 'L01')
assert original.values == (5, 9)
assert reconcile_correction(before, after, receipt) == 1
```

`Archive.open(path)` 重开既有归档。`Archive.initialize(path)` 在空目录中创建存储，在既有归档中保留固定位宽、封批、勘误和回执。指定不同位宽时拒绝。既有卷无法打开时按缺读处理。样例应按需显式封存。

## 接口语义

- `seal_batch(archive, batch)` 接受非空有序来件。批号、行号、请求号均采用 1 至 64 位 ASCII 字母、数字、下划线或连字符，首位为字母或数字。批内行号唯一。每个观测必须是位宽范围内的整数，布尔值拒绝。非法来件报 `InvalidBatch`，批号已占用报 `BatchAlreadyExists`。卷写中断时批号仍保留，成员保持未封，可使用新批号重新归档。成功回执列出原序成员和固定条带地址。`archive.manifest.lookup_batch(batch_id)` 可查已封原序，`lookup_stripe(address)` 可反查原行身份。
- `read_stripe(archive, address)` 返回地址、原行号、所据生效版和 `values`。初版为 1。任一观测卷缺读时用另一观测与校验恢复，校验卷缺读时直接交付两份同版观测。三个字均可读时核对 XOR。未知或未封条带、证据不足时抛出 `StripeUnavailable`。0 是有效读值。
- `apply_correction(archive, request)` 在固定条带上更正一份观测，每条带至多一笔未决。已登记请求可同参重投，也可调用 `resume_correction(archive, request_id)`。卷写分别持久提交，目录生效前仍可领取旧版。生效版和原回执一起提交。同号异参或占用冲突抛出 `RequestConflict`，无效更正报 `InvalidCorrection`，依赖卷或依据暂不可用时可按原号续办。
- `get_receipt(archive, request_id)` 返回 `CorrectionReceipt` 或 `PendingReceipt`。请求未知时抛出 `ReceiptNotFound`。后续勘误保持早先的原回执和其中的版次。
- `audit_batch(archive, batch_id)` 依原序交付 `AuditResult`。合计单位为原始计数，整数精确累加，可超过卷字宽。必要条带不可领取时抛出 `AuditUnavailable`。日账记录每一行的生效版。`reconcile_correction(before, after, receipt)` 核对两份仅相隔该笔勘误的完整日账并返回整数净差，前提或数据不符时抛出 `AuditUnavailable`。

三个卷以独立 SQLite 文件保存固定地址的定宽大端字和版次。目录保存已封成员、生效版、待办和回执。有效位宽之外的填充位必须为零。回归在临时归档中移动实际卷文件模拟缺读，并在真实卷提交与目录提交边界控制恢复和并发读取。
