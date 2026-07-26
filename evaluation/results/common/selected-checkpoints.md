# Common Selected Checkpoints and Provenance

本文记录当前 common selected-checkpoint method-level matrix 使用的 60 个最终 checkpoint。每个 `source_language + method` 只保留一个配置。

## Primary source

```text
open-unlearning-main/saves/exports/common_selected_checkpoint_matrices/<method>/selected_checkpoints.csv
open-unlearning-main/saves/exports/common_selected_checkpoint_matrices/common_selected_checkpoint_profile_metrics.csv
```

本文件中的 `selected_checkpoint` 是根据 `run_name + checkpoint` 还原出的简写路径；源 artifact 中仍保留完整 `checkpoint_dir`。

## Validation

已校验本文档中的 60 个 `source_language + method` checkpoint 与 `selected_checkpoints.csv` 完全一致：

| item | value |
|---|---:|
| expected groups | 60 |
| actual groups | 60 |
| mismatches | 0 |
| profile rows | 600 |
| unique method-source-target cells | 600 |

当前导出的 selected-checkpoint artifact 不包含 `weak_candidate` 字段；因此本文不擅自标注某个最终 checkpoint 是否来自弱候选。弱候选规则见 `evaluation/protocols/common-unlearning-sweep-screening.md`。

## Selected checkpoints

| source_language | method | selected_checkpoint | checkpoint_step | run_name |
| --- | --- | --- | --- | --- |
| ar | ga | ga_ar_lr1e-5/checkpoint-141 | 141 | multilingual_Llama-3.1-8B-Instruct_ga_ar_lr1em5_b8g4_10epoch |
| ar | gd | gd_ar_lr1e-5/checkpoint-47 | 47 | multilingual_Llama-3.1-8B-Instruct_gd_ar_lr1em5_alpha1p0_gamma1p0_b8g4_10epoch |
| ar | npo | npo_ar_lr5e-5_beta0.5/checkpoint-150 | 150 | multilingual_Llama-3.1-8B-Instruct_npo_ar_lr5em5_beta0p5_alpha1p0_gamma1p0_b8g4_10epoch |
| ar | simnpo | simnpo_ar_lr3e-5_beta3.5_gamma0.25/checkpoint-150 | 150 | multilingual_Llama-3.1-8B-Instruct_simnpo_ar_lr3em5_beta3p5_delta1_alpha1p0_gamma0p25_b8g4_10epoch |
| ar | drnpo | drnpo_ar_lr3e-5_beta0.5_dvf2/checkpoint-150 | 150 | multilingual_Llama-3.1-8B-Instruct_drnpo_ar_lr3em5_beta0p5_dvf2_alpha1p0_gamma1p0_b8g4_10epoch |
| ar | drsimnpo | drsimnpo_ar_lr5e-5_beta4.5_sf5_gamma0.25/checkpoint-150 | 150 | multilingual_Llama-3.1-8B-Instruct_drsimnpo_ar_lr5em5_beta4p5_delta1_sf5_alpha1p0_gamma0p25_b8g4_10epoch |
| bn | ga | ga_bn_lr1e-5/checkpoint-78 | 78 | multilingual_Llama-3.1-8B-Instruct_ga_bn_lr1em5_b8g4_10epoch |
| bn | gd | gd_bn_lr1e-5/checkpoint-31 | 31 | multilingual_Llama-3.1-8B-Instruct_gd_bn_lr1em5_alpha1p0_gamma1p0_b8g4_10epoch |
| bn | npo | npo_bn_lr3e-5_beta0.5/checkpoint-141 | 141 | multilingual_Llama-3.1-8B-Instruct_npo_bn_lr3em5_beta0p5_alpha1p0_gamma1p0_b8g4_10epoch |
| bn | simnpo | simnpo_bn_lr3e-5_beta3.5_gamma0.125/checkpoint-150 | 150 | multilingual_Llama-3.1-8B-Instruct_simnpo_bn_lr3em5_beta3p5_delta1_alpha1p0_gamma0p125_b8g4_10epoch |
| bn | drnpo | drnpo_bn_lr3e-5_beta0.5_dvf5/checkpoint-150 | 150 | multilingual_Llama-3.1-8B-Instruct_drnpo_bn_lr3em5_beta0p5_dvf5_alpha1p0_gamma1p0_b8g4_10epoch |
| bn | drsimnpo | drsimnpo_bn_lr3e-5_beta4.5_sf5_gamma0.25/checkpoint-150 | 150 | multilingual_Llama-3.1-8B-Instruct_drsimnpo_bn_lr3em5_beta4p5_delta1_sf5_alpha1p0_gamma0p25_b8g4_10epoch |
| de | ga | ga_de_lr3e-5/checkpoint-15 | 15 | multilingual_Llama-3.1-8B-Instruct_ga_de_lr3em5_b8g4_10epoch |
| de | gd | gd_de_lr1e-5/checkpoint-94 | 94 | multilingual_Llama-3.1-8B-Instruct_gd_de_lr1em5_alpha1p0_gamma1p0_b8g4_10epoch |
| de | npo | npo_de_lr3e-5_beta0.5/checkpoint-150 | 150 | multilingual_Llama-3.1-8B-Instruct_npo_de_lr3em5_beta0p5_alpha1p0_gamma1p0_b8g4_10epoch |
| de | simnpo | simnpo_de_lr5e-5_beta3.5_gamma0.25/checkpoint-150 | 150 | multilingual_Llama-3.1-8B-Instruct_simnpo_de_lr5em5_beta3p5_delta1_alpha1p0_gamma0p25_b8g4_10epoch |
| de | drnpo | drnpo_de_lr3e-5_beta0.1_dvf5/checkpoint-150 | 150 | multilingual_Llama-3.1-8B-Instruct_drnpo_de_lr3em5_beta0p1_dvf5_alpha1p0_gamma1p0_b8g4_10epoch |
| de | drsimnpo | drsimnpo_de_lr3e-5_beta3.5_sf5_gamma0.25/checkpoint-141 | 141 | multilingual_Llama-3.1-8B-Instruct_drsimnpo_de_lr3em5_beta3p5_delta1_sf5_alpha1p0_gamma0p25_b8g4_10epoch |
| en | ga | ga_en_lr1e-5/checkpoint-150 | 150 | multilingual_Llama-3.1-8B-Instruct_ga_en_lr1em5_b8g4_10epoch |
| en | gd | gd_en_lr1e-5/checkpoint-78 | 78 | multilingual_Llama-3.1-8B-Instruct_gd_en_lr1em5_alpha1p0_gamma1p0_b8g4_10epoch |
| en | npo | npo_en_lr3e-5_beta0.1/checkpoint-150 | 150 | multilingual_Llama-3.1-8B-Instruct_npo_en_lr3em5_beta0p1_alpha1p0_gamma1p0_b8g4_10epoch |
| en | simnpo | simnpo_en_lr5e-5_beta3.5_gamma0.25/checkpoint-150 | 150 | multilingual_Llama-3.1-8B-Instruct_simnpo_en_lr5em5_beta3p5_delta1_alpha1p0_gamma0p25_b8g4_10epoch |
| en | drnpo | drnpo_en_lr3e-5_beta0.1_dvf5/checkpoint-150 | 150 | multilingual_Llama-3.1-8B-Instruct_drnpo_en_lr3em5_beta0p1_dvf5_alpha1p0_gamma1p0_b8g4_10epoch |
| en | drsimnpo | drsimnpo_en_lr5e-5_beta3.5_sf5_gamma0.25/checkpoint-150 | 150 | multilingual_Llama-3.1-8B-Instruct_drsimnpo_en_lr5em5_beta3p5_delta1_sf5_alpha1p0_gamma0p25_b8g4_10epoch |
| es | ga | ga_es_lr3e-5/checkpoint-15 | 15 | multilingual_Llama-3.1-8B-Instruct_ga_es_lr3em5_b8g4_10epoch |
| es | gd | gd_es_lr3e-5/checkpoint-141 | 141 | multilingual_Llama-3.1-8B-Instruct_gd_es_lr3em5_alpha1p0_gamma1p0_b8g4_10epoch |
| es | npo | npo_es_lr3e-5_beta0.1/checkpoint-141 | 141 | multilingual_Llama-3.1-8B-Instruct_npo_es_lr3em5_beta0p1_alpha1p0_gamma1p0_b8g4_10epoch |
| es | simnpo | simnpo_es_lr3e-5_beta3.5_gamma0.25/checkpoint-150 | 150 | multilingual_Llama-3.1-8B-Instruct_simnpo_es_lr3em5_beta3p5_delta1_alpha1p0_gamma0p25_b8g4_10epoch |
| es | drnpo | drnpo_es_lr3e-5_beta0.1_dvf2/checkpoint-150 | 150 | multilingual_Llama-3.1-8B-Instruct_drnpo_es_lr3em5_beta0p1_dvf2_alpha1p0_gamma1p0_b8g4_10epoch |
| es | drsimnpo | drsimnpo_es_lr3e-5_beta4.5_sf2_gamma0.25/checkpoint-150 | 150 | multilingual_Llama-3.1-8B-Instruct_drsimnpo_es_lr3em5_beta4p5_delta1_sf2_alpha1p0_gamma0p25_b8g4_10epoch |
| fr | ga | ga_fr_lr1e-5/checkpoint-126 | 126 | multilingual_Llama-3.1-8B-Instruct_ga_fr_lr1em5_b8g4_10epoch |
| fr | gd | gd_fr_lr1e-5/checkpoint-94 | 94 | multilingual_Llama-3.1-8B-Instruct_gd_fr_lr1em5_alpha1p0_gamma1p0_b8g4_10epoch |
| fr | npo | npo_fr_lr3e-5_beta0.5/checkpoint-150 | 150 | multilingual_Llama-3.1-8B-Instruct_npo_fr_lr3em5_beta0p5_alpha1p0_gamma1p0_b8g4_10epoch |
| fr | simnpo | simnpo_fr_lr3e-5_beta4.5_gamma0.125/checkpoint-150 | 150 | multilingual_Llama-3.1-8B-Instruct_simnpo_fr_lr3em5_beta4p5_delta1_alpha1p0_gamma0p125_b8g4_10epoch |
| fr | drnpo | drnpo_fr_lr3e-5_beta0.5_dvf2/checkpoint-150 | 150 | multilingual_Llama-3.1-8B-Instruct_drnpo_fr_lr3em5_beta0p5_dvf2_alpha1p0_gamma1p0_b8g4_10epoch |
| fr | drsimnpo | drsimnpo_fr_lr3e-5_beta4.5_sf5_gamma0.25/checkpoint-150 | 150 | multilingual_Llama-3.1-8B-Instruct_drsimnpo_fr_lr3em5_beta4p5_delta1_sf5_alpha1p0_gamma0p25_b8g4_10epoch |
| ja | ga | ga_ja_lr3e-5/checkpoint-15 | 15 | multilingual_Llama-3.1-8B-Instruct_ga_ja_lr3em5_b8g4_10epoch |
| ja | gd | gd_ja_lr1e-5/checkpoint-47 | 47 | multilingual_Llama-3.1-8B-Instruct_gd_ja_lr1em5_alpha1p0_gamma1p0_b8g4_10epoch |
| ja | npo | npo_ja_lr3e-5_beta0.1/checkpoint-150 | 150 | multilingual_Llama-3.1-8B-Instruct_npo_ja_lr3em5_beta0p1_alpha1p0_gamma1p0_b8g4_10epoch |
| ja | simnpo | simnpo_ja_lr5e-5_beta3.5_gamma0.25/checkpoint-141 | 141 | multilingual_Llama-3.1-8B-Instruct_simnpo_ja_lr5em5_beta3p5_delta1_alpha1p0_gamma0p25_b8g4_10epoch |
| ja | drnpo | drnpo_ja_lr5e-5_beta0.1_dvf2/checkpoint-150 | 150 | multilingual_Llama-3.1-8B-Instruct_drnpo_ja_lr5em5_beta0p1_dvf2_alpha1p0_gamma1p0_b8g4_10epoch |
| ja | drsimnpo | drsimnpo_ja_lr5e-5_beta3.5_sf2_gamma0.25/checkpoint-150 | 150 | multilingual_Llama-3.1-8B-Instruct_drsimnpo_ja_lr5em5_beta3p5_delta1_sf2_alpha1p0_gamma0p25_b8g4_10epoch |
| sw | ga | ga_sw_lr1e-5/checkpoint-94 | 94 | multilingual_Llama-3.1-8B-Instruct_ga_sw_lr1em5_b8g4_10epoch |
| sw | gd | gd_sw_lr1e-5/checkpoint-47 | 47 | multilingual_Llama-3.1-8B-Instruct_gd_sw_lr1em5_alpha1p0_gamma1p0_b8g4_10epoch |
| sw | npo | npo_sw_lr3e-5_beta0.5/checkpoint-150 | 150 | multilingual_Llama-3.1-8B-Instruct_npo_sw_lr3em5_beta0p5_alpha1p0_gamma1p0_b8g4_10epoch |
| sw | simnpo | simnpo_sw_lr3e-5_beta3.5_gamma0.25/checkpoint-150 | 150 | multilingual_Llama-3.1-8B-Instruct_simnpo_sw_lr3em5_beta3p5_delta1_alpha1p0_gamma0p25_b8g4_10epoch |
| sw | drnpo | drnpo_sw_lr3e-5_beta0.1_dvf2/checkpoint-150 | 150 | multilingual_Llama-3.1-8B-Instruct_drnpo_sw_lr3em5_beta0p1_dvf2_alpha1p0_gamma1p0_b8g4_10epoch |
| sw | drsimnpo | drsimnpo_sw_lr3e-5_beta3.5_sf5_gamma0.25/checkpoint-141 | 141 | multilingual_Llama-3.1-8B-Instruct_drsimnpo_sw_lr3em5_beta3p5_delta1_sf5_alpha1p0_gamma0p25_b8g4_10epoch |
| th | ga | ga_th_lr1e-5/checkpoint-110 | 110 | multilingual_Llama-3.1-8B-Instruct_ga_th_lr1em5_b8g4_10epoch |
| th | gd | gd_th_lr3e-5/checkpoint-15 | 15 | multilingual_Llama-3.1-8B-Instruct_gd_th_lr3em5_alpha1p0_gamma1p0_b8g4_10epoch |
| th | npo | npo_th_lr5e-5_beta0.1/checkpoint-150 | 150 | multilingual_Llama-3.1-8B-Instruct_npo_th_lr5em5_beta0p1_alpha1p0_gamma1p0_b8g4_10epoch |
| th | simnpo | simnpo_th_lr3e-5_beta4.5_gamma0.25/checkpoint-150 | 150 | multilingual_Llama-3.1-8B-Instruct_simnpo_th_lr3em5_beta4p5_delta1_alpha1p0_gamma0p25_b8g4_10epoch |
| th | drnpo | drnpo_th_lr5e-5_beta0.1_dvf5/checkpoint-150 | 150 | multilingual_Llama-3.1-8B-Instruct_drnpo_th_lr5em5_beta0p1_dvf5_alpha1p0_gamma1p0_b8g4_10epoch |
| th | drsimnpo | drsimnpo_th_lr3e-5_beta3.5_sf5_gamma0.25/checkpoint-141 | 141 | multilingual_Llama-3.1-8B-Instruct_drsimnpo_th_lr3em5_beta3p5_delta1_sf5_alpha1p0_gamma0p25_b8g4_10epoch |
| zh | ga | ga_zh_lr3e-5/checkpoint-15 | 15 | multilingual_Llama-3.1-8B-Instruct_ga_zh_lr3em5_b8g4_10epoch |
| zh | gd | gd_zh_lr1e-5/checkpoint-47 | 47 | multilingual_Llama-3.1-8B-Instruct_gd_zh_lr1em5_alpha1p0_gamma1p0_b8g4_10epoch |
| zh | npo | npo_zh_lr3e-5_beta0.5/checkpoint-141 | 141 | multilingual_Llama-3.1-8B-Instruct_npo_zh_lr3em5_beta0p5_alpha1p0_gamma1p0_b8g4_10epoch |
| zh | simnpo | simnpo_zh_lr5e-5_beta3.5_gamma0.25/checkpoint-141 | 141 | multilingual_Llama-3.1-8B-Instruct_simnpo_zh_lr5em5_beta3p5_delta1_alpha1p0_gamma0p25_b8g4_10epoch |
| zh | drnpo | drnpo_zh_lr5e-5_beta0.1_dvf2/checkpoint-150 | 150 | multilingual_Llama-3.1-8B-Instruct_drnpo_zh_lr5em5_beta0p1_dvf2_alpha1p0_gamma1p0_b8g4_10epoch |
| zh | drsimnpo | drsimnpo_zh_lr3e-5_beta3.5_sf5_gamma0.25/checkpoint-141 | 141 | multilingual_Llama-3.1-8B-Instruct_drsimnpo_zh_lr3em5_beta3p5_delta1_sf5_alpha1p0_gamma0p25_b8g4_10epoch |

## Result provenance

原始 selected-config 结果主要来自：

```text
open-unlearning-main/saves/exports/new_export/common_culture_selected_config_10lang_6method_results.xlsx
```

下列 `source_language + method` 因主 workbook 中效果不理想进行了重跑，重跑结果保存在 `new_export` 下对应 Excel 文件中，并已进入当前 selected-checkpoint/profile artifact：

| source_language | rerun methods |
| --- | --- |
| ar | ga, simnpo, drsimnpo |
| bn | gd |
| de | npo, simnpo |
| en | ga, gd, npo, simnpo, drnpo, drsimnpo |
| es | npo, drnpo |
| fr | simnpo |
| ja | gd, drsimnpo |
| sw | ga, simnpo, drsimnpo |
| th | npo, simnpo, drnpo |
| zh | simnpo, drsimnpo |

重跑 workbook 包括：

```text
ar_ga_simnpo_drsimnpo_all_results.xlsx
bn_gd_selected_results.xlsx
common_culture_en_6methods_screening.xlsx
de_npo_simnpo_all_results.xlsx
es_npo_drnpo_fr_simnpo_all_results.xlsx
ja_gd_drsimnpo_all_results.xlsx
sw_ga_simnpo_drsimnpo_all_results.xlsx
th_npo_simnpo_drnpo_zh_simnpo_drsimnpo_all_results.xlsx
```
