# R03 冷卷勘误错读

在仓库根目录执行 `python3 -B -m unittest tests.test_amendment.AmendmentTests.test_half_write`。原回归在临时归档中封存 R03 `(5, 9)`，发起 C01 将首值改为 6。它在第一卷提交后暂停更正，让第二卷暂不可读，然后发起一次条带领取。

事故中领取标作版次 1，读值却为 `(6, 10)`，核验输出 `STRIPE_MIXED_REV`。此时 C01 尚未生效，领取应为版次 1 的 R03 `(5, 9)`，单行账为 14。恢复第二卷并完成更正后，应领到版次 2 的 R03 `(6, 9)`，单行账为 15，C01 可凭原请求领取成功回执。

`python3 -B check_project.py` 运行完整原回归。`python3 -B -m samples.demo` 演示包含 R20、R03 的全批交班。正确的全批合计在勘误前和暂停期间均为 21，生效后为 22。
