from src.datasets.pornography_frame_dataset import PornographyFrameDataset

import os
from typing import Dict, List, Union, Optional
import pandas as pd
from sklearn.model_selection import train_test_split
import albumentations as A
from albumentations.pytorch import ToTensorV2

from torch.utils.data import DataLoader


def split_data(
    df_frames: pd.DataFrame, split_sizes: List[float]
) -> Dict[str, pd.DataFrame]:
    df_frames["video"] = [frame_name.split("#")[0] for frame_name in df_frames["frame"]]

    agg = {"video": "first", "label": "first"}

    df_videos = df_frames[["video", "label"]]
    df_videos = df_videos.groupby("video").aggregate(agg).reset_index(drop=True)

    df_frames = df_frames.drop("video", axis=1)

    val_size, test_size = split_sizes
    real_val_size = (1 - test_size) * val_size

    train_videos, test_videos = train_test_split(df_videos, test_size=test_size, random_state=42)
    train_videos, val_videos = train_test_split(train_videos, test_size=real_val_size, random_state=42)

    train_frames = df_frames[df_frames["frame"].str.contains("|".join(train_videos["video"]))]
    val_frames = df_frames[df_frames["frame"].str.contains("|".join(val_videos["video"]))]
    test_frames = df_frames[df_frames["frame"].str.contains("|".join(test_videos["video"]))]

    split = {"train": train_frames, "val": val_frames, "test": test_frames}
    print(f"Created split.")
    log_split(split)

    return split


def load_split(
    data_loc: str, 
    split_sizes: List[float], 
    partitions: Optional[Union[str, List[str]]] = None
) -> Dict[str, pd.DataFrame]:
    df = pd.read_csv(f"{data_loc}/split_{int(split_sizes[0]*100)}_{int(split_sizes[1]*100)}.csv")
    
    if not partitions:
        partitions = list(df["partition"].unique())
    
    if isinstance(partitions, str):
        partitions = [partitions]

    split = {p: df[df["partition"] == p] for p in partitions}
    print("Loaded split.")
    log_split(split)

    return split


def save_split(
    save_loc: str,
    split_sizes: List[float],
    partitions: List[str],
    dfs: Dict[str, pd.DataFrame],
):
    for p in partitions:
        dfs[p]["partition"] = p
    
    split = pd.concat(dfs.values(), ignore_index=True)
    split.to_csv(
        f"{save_loc}/split_{int(split_sizes[0]*100)}_{int(split_sizes[1]*100)}.csv",
        index=False,
    )


def check_split(data_loc: str, split_sizes: List[float]) -> bool:
    return os.path.isfile(f"{data_loc}/split_{int(split_sizes[0]*100)}_{int(split_sizes[1]*100)}.csv")


def log_split(split: Dict[str, pd.DataFrame]):
    for partition, df in split.items():
        print(f"{partition}: total ({len(df)}); porn ({len(df[df['label'] == 1])}); non-porn ({len(df[df['label'] == 0])})")


def get_transforms(
    data_aug: bool,
    input_shape: int,
    norm_mean: List[float] = None,
    norm_std: List[float] = None,
) -> Dict[str, A.Compose]:

    train_transforms = [
        A.RandomCropFromBorders(),
        A.Resize(height=input_shape, width=input_shape),
        A.RandomRotate90(),
        A.ColorJitter(),
        A.RandomGamma(),
    ]

    val_and_test_transforms = [
        A.Resize(height=input_shape, width=input_shape),
    ]

    if norm_mean is not None and norm_std is not None:
        train_transforms.append(A.Normalize(mean=norm_mean, std=norm_std))
        val_and_test_transforms.append(A.Normalize(mean=norm_mean, std=norm_std))

    train_transforms.append(ToTensorV2())
    val_and_test_transforms.append(ToTensorV2())

    return {
        "train": A.Compose(train_transforms if data_aug else val_and_test_transforms),
        "val": A.Compose(val_and_test_transforms),
        "test": A.Compose(val_and_test_transforms),
    }


def init_data(
    data_loc: str,
    data_aug: bool,
    batch_size: int,
    split_sizes: List[float],
    input_shape: int,
    norm_mean: List[float],
    norm_std: List[float],
    shuffle_dataloader: bool = False,
):
    data_transforms = get_transforms(data_aug, input_shape, norm_mean, norm_std)

    df_frames = pd.read_csv(f"{data_loc}/data.csv")

    partitions = ["train", "val", "test"]
    if not check_split(data_loc, split_sizes):
        dfs = split_data(df_frames, split_sizes)
        save_split(data_loc, split_sizes, partitions, dfs)
    else:
        dfs = load_split(data_loc, split_sizes)

    datasets = {
        p: PornographyFrameDataset(data_loc, dfs[p], data_transforms.get(p))
        for p in partitions
    }
    dataloaders = {
        p: DataLoader(
            dataset=datasets[p], 
            batch_size=batch_size, 
            shuffle=shuffle_dataloader,
            num_workers=8, 
            pin_memory=True
        )
        for p in partitions
    }
    dataset_sizes = {p: len(datasets[p]) for p in partitions}

    return dataloaders, dataset_sizes
