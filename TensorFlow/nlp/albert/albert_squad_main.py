###############################################################################
# Copyright (C) 2020-2021 Habana Labs, Ltd. an Intel Company
###############################################################################

import os
import sys
from pathlib import Path
import subprocess
from central.habana_model_runner_utils import HabanaEnvVariables, print_env_info, get_canonical_path, get_canonical_path_str, is_valid_multi_node_config, get_multi_node_config_nodes
from central.training_run_config import TrainingRunHWConfig
from central.multi_node_utils import run_per_ip
import TensorFlow.nlp.bert.prepare_output_dir_squad as prepare_output_dir_squad

class AlbertFinetuningSQUAD(TrainingRunHWConfig):
    def __init__(self, scaleout, num_workers_per_hls, hls_type, kubernetes_run, args, epochs, batch_size, max_seq_len, pretrained_model, enable_scoped_allocator):
        super(AlbertFinetuningSQUAD, self).__init__(scaleout, num_workers_per_hls, hls_type, kubernetes_run, "demo_albert_log")
        self.args = args
        self.epochs = epochs
        self.batch_size = batch_size
        self.max_seq_len = max_seq_len
        self.pretrained_model = pretrained_model
        self.enable_scoped_allocator = enable_scoped_allocator
        self.command = ''
        self.squad_habana_env_variables = {}
        if self.args.dataset_path is None:
            self.args.dataset_path = Path(__file__).parent.joinpath("data")

    def prepare_output_dir(self):
        try:
            if self.scaleout and is_valid_multi_node_config() and not self.kubernetes_run:
                prepare_output_dir_squad_path = Path(__file__).parent.joinpath('prepare_output_dir_squad.py')
                run_per_ip(f"{sys.executable} {str(prepare_output_dir_squad_path)} {self.args.output_dir} {self.batch_size} {self.max_seq_len}", ['MULTI_HLS_IPS', 'PYTHONPATH'], False)
            else:
                prepare_output_dir_squad.prepare_output_dir_squad_r(self.args.output_dir, self.batch_size, self.max_seq_len)
        except Exception as exc:
            raise RuntimeError(f"Error in {self.__class__.__name__} prepare_output_dir()") from exc

    def build_command(self):
        try:
            run_squad_path = Path(__file__).parent.joinpath('run_squad_v1.py')
            pretrained_model_path = get_canonical_path(self.pretrained_model)
            use_horovod_str = "true" if self.scaleout else "false"
            vocab_path = str(pretrained_model_path.joinpath("30k-clean.vocab"))
            spm_path = str(pretrained_model_path.joinpath("30k-clean.model"))
            bcfg_path = str(pretrained_model_path.joinpath("albert_config.json"))
            ic_path = str(pretrained_model_path.joinpath("model.ckpt-best"))
            squad_train_file = get_canonical_path(self.args.dataset_path).joinpath('train-v1.1.json')
            squad_predict_file = get_canonical_path(self.args.dataset_path).joinpath('dev-v1.1.json')
            train_feature_file = get_canonical_path_str(self.args.output_dir) + "/train_feature_file.tf_record"
            predict_feature_file = get_canonical_path_str(self.args.output_dir) + "/predict_feature_file.tf_record"
            predict_feature_left_file = get_canonical_path_str(self.args.output_dir) + "/predict_feature_left_file.tf_record"

            print(f"{self.__class__.__name__}: self.mpirun_cmd = {self.mpirun_cmd}")
            if self.mpirun_cmd == '':
                init_command = f"time python3 {str(run_squad_path)}"
            else:
                init_command = f"time {self.mpirun_cmd} python3 {str(run_squad_path)}"
            self.command = (
                f"{init_command}"
                f" --train_feature_file={train_feature_file}"
                f" --predict_feature_file={predict_feature_file}"
                f" --predict_feature_left_file={predict_feature_left_file}"
                f" --spm_model_file={spm_path}"
                f" --vocab_file={vocab_path}"
                f" --albert_config_file={bcfg_path}"
                f" --init_checkpoint={ic_path}"
                f" --do_train=True"
                f" --train_file={squad_train_file}"
                f" --do_predict=True"
                f" --predict_file={squad_predict_file}"
                f" --train_batch_size={self.batch_size}"
                f" --learning_rate={self.args.learning_rate}"
                f" --num_train_epochs={self.epochs}"
                f" --max_seq_length={self.max_seq_len}"
                f" --doc_stride=128"
                f" --output_dir={get_canonical_path_str(self.args.output_dir)}"
                f" --use_horovod={use_horovod_str}"
                f" --enable_scoped_allocator={self.enable_scoped_allocator}"
            )
            print('albert_squad_utils::self.command = ', self.command)
        except Exception as exc:
            raise RuntimeError(f"Error in {self.__class__.__name__} build_command()") from exc

    def run(self):
        try:
            self.prepare_output_dir()
            print("*** Running ALBERT training...\n\n")

            run_config_env_vars = self.get_env_vars()
            print('run_config_env_vars = ', run_config_env_vars)
            with HabanaEnvVariables(env_vars_to_set=run_config_env_vars), \
                 HabanaEnvVariables(env_vars_to_set=self.squad_habana_env_variables):
                self.build_command()
                print_env_info(self.command, run_config_env_vars)
                print_env_info(self.command, self.squad_habana_env_variables)
                print(f"{self.__class__.__name__} run(): self.command = {self.command}")
                sys.stdout.flush()
                sys.stderr.flush()
                with subprocess.Popen(self.command, shell=True, executable='/bin/bash') as proc:
                    proc.wait()
        except Exception as exc:
            raise RuntimeError(f"Error in {self.__class__.__name__} run()") from exc
