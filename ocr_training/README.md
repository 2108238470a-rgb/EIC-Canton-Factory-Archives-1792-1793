# 历史档案 OCR 标注与微调包

**交给历史工作者：先读 `01_给标注者的规范.md` 和 `02_填写范本.md`，填写实际标注包中的 `annotations.csv`。不需要安装训练软件。**

已准备真实试标包：`packages/doc58-pilot-40pages/`，含第 58 号档案 40 页、136 个区域的图像和空白转录表。所有记录都是 draft，尚无人工真值。它是单卷试标与基线包，不能单独证明跨卷泛化，也不能直接作为完整训练/验证/测试集。

`packages/给历史工作者_doc58试标包.zip` 是可直接转交的压缩包，含区域图、全页图、空表、清单及两份中文说明，不包含 OCR 提示文本。原包另存的 OCR hints 仅供后续复核，不能直接复制为真值。

- `01_给标注者的规范.md`：逐字转录、疑难字、姓名数字、状态与复核。
- `02_填写范本.md`：教学示例，明确不是档案事实或已标注训练数据。
- `03_A6000训练步骤.md`：独立训练环境、数据检查、冒烟训练、评测与发布。
- `04_跨卷提示词配置.md`：当前软件的文献配置方式。
- `templates/`：空表与分组表范本。
- `scripts/prepare_packet.py`：从现有 pilot.json 复制页图并生成区域图，不调用 OCR/LLM，不写数据库。
- `scripts/export_dataset.py`：检查独立复核、图像哈希及分组隔离，导出 ERNIEKit 格式和独立校正配对。
- `scripts/build_training_config.py`：基于官方配置生成 A6000 冒烟配置；不会启动训练。
- `packages/`、`exports/`：包含档案与人工标注，保持本地，不提交 Git。

## 工作者完成后，技术人员执行

在项目根目录，先检查，不导出：

```sh
python ocr_training/scripts/export_dataset.py \
  --packet ocr_training/packages/doc58-pilot-40pages --check-only
```

单卷包允许检查，但正式导出要求至少三个独立分组分别进入训练、验证、测试集。扩充其他卷后，重新建立一个合并标注包，再填写它自己的表；不要用新生成的空表覆盖已经填写的表。已填表可按稳定 sample_id 由技术人员合并，人工复核后再导出。

```sh
python ocr_training/scripts/prepare_packet.py \
  --pilot /path/volume-A/pilot.json \
  --pilot /path/volume-B/pilot.json \
  --pilot /path/volume-C/pilot.json \
  --output ocr_training/packages/multivolume-v1

python ocr_training/scripts/export_dataset.py \
  --packet ocr_training/packages/multivolume-v1 \
  --splits /path/reviewed-splits.csv \
  --output ocr_training/exports/history-v1
```

`split_group` 默认按档案 ID，但同一实体卷册重复上传、同一书写者的相关材料必须合并分组；不能把同卷相邻页随机分给不同集合。工具检查同一 volume_id、已知 writer_group、相同页图及区域图跨集合的泄漏；近似重复页仍需人工排查。

数据集导出不等于模型可训练：目标区域必须完整、与处理器输入对应，且目标序列不能被截断。训练版本兼容、显存与保存重载检查见第三份说明。
