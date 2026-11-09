# Protein Engineering 数据字典（Phase 0）

## 1. 设计原则

- 一个靶标（target）可以有 WT、多个设计变体和对照变体。
- 一个变体（variant）可以制备出多个物理样品（sample）；样品不是序列本身。
- 一个实验批次（batch）可以包含多个样品、对照和读数。
- 原始观测与计算结果分开保存；AI 预测与湿实验实测分开保存。
- 每个结果尽可能保留来源；不覆盖原始文件，不把缺失值填成 0。
- CSV 模板只定义字段，不代表任何真实实验数据已经收到。

## 2. 通用规则

| 规则 | 定义 |
| --- | --- |
| ID | 稳定、唯一、不可复用；不把姓名或敏感信息写入 ID。 |
| 时间 | ISO 8601 UTC，例如 `2026-11-07T08:30:00Z`；如有需要另存原始本地时间和时区。 |
| 数值 | 数值列只存数值；单位放独立字段。 |
| 缺失值 | 空单元格代表未知/未提供；不得用 0、平均值或模型预测值代替。 |
| 单位 | 尽可能保留原始数值和单位；标准化换算另存并记录方法。 |
| 序列 | 保留原始来源；规范化副本使用大写单字母氨基酸代码，并记录规范化规则。 |
| 哈希 | 对文件和规范化序列计算 SHA-256。 |
| 重复 | 明确区分独立生物学重复与同一样品的技术重复。 |
| 来源 | 文件型数据关联 `source_file_id`；尽量保留工作表、行号、孔位和原始文件名。 |

## 3. 数据实体与字段

### `enzyme_targets_template.csv` — 靶标

| 字段 | 含义 |
| --- | --- |
| `target_id` | 靶标唯一 ID，必填、唯一 |
| `target_name` | 名称或实验室内部名称，必填 |
| `ec_number` | EC 编号，可选 |
| `organism` | 来源物种/菌株 |
| `source_accession` / `source_database` | 数据库 accession 及来源数据库 |
| `reference_sequence_variant_id` | 作为参考的 WT/参考变体 ID |
| `source_file_id` / `notes` | 来源文件与备注 |

### `protein_variants_template.csv` — 序列与变体

| 字段 | 含义 |
| --- | --- |
| `variant_id` / `target_id` | 变体唯一 ID / 所属靶标 ID，必填 |
| `variant_name` | WT/候选/对照名称，必填 |
| `variant_role` | `WT`、`DESIGNED`、`CONTROL`、`REFERENCE` 或 `OTHER` |
| `parent_variant_id` | 设计来源亲本变体 |
| `reference_variant_id` | 用于突变比较的参考变体，候选建议填写 |
| `sequence` / `sequence_sha256` | 氨基酸序列 / 规范化序列哈希 |
| `mutation_notation_as_reported` | 合作方或模型给出的原始突变描述 |
| `numbering_reference` | 全长前体、成熟蛋白、构建体或结构编号体系 |
| `design_id` / `design_round` | AI 设计任务 ID / 设计轮次 |
| `design_method` / `design_method_version` | 设计工具或方法及版本 |
| `model_name` / `model_version` | 模型名称及版本/checkpoint |
| `design_objective` / `generated_at_utc` | 设计目标 / 候选生成时间 |
| `source_file_id` / `source_record_id` / `notes` | 来源文件、来源记录和备注 |

**突变解释：** 不仅凭文本标签确认突变。导入后应将变体序列与明确参考序列比对，再生成标准化突变清单。插入、缺失、组合突变、信号肽/标签差异必须保留比对上下文。不得混用前体、成熟蛋白和 PDB 编号。

### `samples_template.csv` — 物理样品

`sample_id`（唯一 ID，必填）、`variant_id`（对应变体，必填）、`sample_lot_id`（批号）、`biological_replicate`（独立制备重复）、`expression_host`、`expression_system`、`construct_tag`、`purification_method`、`purification_protocol_version`、`concentration_value`、`concentration_unit`、`purity_percent`、`storage_buffer`、`storage_temperature_c`、`storage_duration`、`freeze_thaw_cycles`、`prepared_at_utc`、`source_file_id`、`notes`。

### `experiment_batches_template.csv` — 实验批次和条件

`batch_id`（唯一 ID，必填）、`assay_id`（检测任务，必填）、`assay_type`（检测类型，必填）、`protocol_id`、`protocol_version`、`run_date_utc`、`operator_code`（匿名代码）、`instrument_id`、`instrument_model`、`plate_id`、`temperature_c`、`pH`、`buffer_composition`、`substrate_name`、`substrate_lot`、`cofactor_name`、`cofactor_concentration`、`cofactor_concentration_unit`、`enzyme_concentration`、`enzyme_concentration_unit`、`reaction_volume`、`reaction_volume_unit`、`readout_method`、`calibration_method`、`wt_control_sample_id`、`blank_control_id`、`positive_control_id`、`source_file_id`、`notes`。

### `kinetic_timecourse_template.csv` — 动力学原始时间序列

每行代表一个样品/孔位在一个时间点的一次观测；同一反应孔的多个时间点使用相同 batch/sample/well 标识。

`observation_id`（唯一 ID，必填）、`batch_id`、`sample_id`、`well_id`、`biological_replicate`、`technical_replicate`、`substrate_concentration`、`substrate_concentration_unit`、`time_value`、`time_unit`、`raw_signal`、`signal_unit`、`blank_signal`、`corrected_signal`、`product_concentration`、`product_concentration_unit`、`source_file_id`、`source_sheet`、`source_row`、`notes`。

原始信号应尽量保留。校正信号和产物浓度只有在来源数据/校准方法明确时填写，并记录处理方法。

### `assay_results_template.csv` — 终点或已报告结果

`result_id`（唯一 ID，必填）、`batch_id`、`sample_id`、`metric_name`、`metric_value`、`metric_unit`、`biological_replicate`、`technical_replicate`、`condition_id`、`measurement_method`、`source_file_id`、`source_sheet`、`source_row`、`notes`。

保存实验方直接报告的结果。平台后续拟合产生的参数应另存为带算法版本、输入记录和拟合诊断的派生结果，不覆盖原始结果。

### `ai_predictions_template.csv` — AI 预测

`prediction_id`（唯一 ID，必填）、`design_id`、`variant_id`、`predicted_metric`、`predicted_value`、`predicted_unit`、`prediction_type`（数值/分类/排序/模型分数）、`prediction_direction`（优劣方向）、`rank_within_design`、`uncertainty_value`、`uncertainty_type`、`model_name`、`model_version`、`method_name`、`method_version`、`run_timestamp_utc`、`input_sequence_sha256`、`raw_output_file`、`source_file_id`、`source_record_id`、`notes`。

### `structure_assets_template.csv` — 结构文件索引

`structure_id`（唯一 ID，必填）、`variant_id`、`structure_source`（实验/预测/其他）、`structure_method`、`method_version`、`structure_file`、`structure_format`（PDB/mmCIF 等）、`source_accession`、`confidence_metric`、`confidence_value`、`chain_id`、`residue_numbering_reference`、`sequence_sha256`、`created_at_utc`、`source_file_id`、`notes`。

### `source_manifest_template.csv` — 文件来源与权限

`source_file_id`（唯一 ID，必填）、`file_name`、`file_type`、`source_system`、`received_at_utc`、`provided_by_role`（团队/角色匿名标识）、`sha256`、`permission_status`、`confidentiality_class`、`contains_personal_data`、`notes`。

## 4. 导入顺序与存储

1. 先导入 target 和 variant，再导入 sample、batch，最后导入原始观测、结果、预测和结构索引。
2. 导入时验证主键、外键、序列格式、单位、时间戳、重复记录和文件来源。
3. 原始仪器文件保持只读；模板是结构化导入入口，不替代原始文件。
4. 公开仓库只保存空模板和文档。未公开序列、实验原始数据、结构文件和模型输出放在受控存储中。
