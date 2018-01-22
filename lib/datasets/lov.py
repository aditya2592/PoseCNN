__author__ = 'yuxiang'

import os
import datasets
import datasets.lov
import datasets.imdb
import cPickle
import numpy as np
import cv2
from fcn.config import cfg
from utils.pose_error import *
from transforms3d.quaternions import quat2mat, mat2quat

class lov(datasets.imdb):
    def __init__(self, image_set, lov_path = None):
        datasets.imdb.__init__(self, 'lov_' + image_set)
        self._image_set = image_set
        self._lov_path = self._get_default_path() if lov_path is None \
                            else lov_path
        self._data_path = os.path.join(self._lov_path, 'data')

        self._classes = ('__background__', '002_master_chef_can', '003_cracker_box', '004_sugar_box', '005_tomato_soup_can', '006_mustard_bottle', \
                         '007_tuna_fish_can', '008_pudding_box', '009_gelatin_box', '010_potted_meat_can', '011_banana', '019_pitcher_base', \
                         '021_bleach_cleanser', '024_bowl', '025_mug', '035_power_drill', '036_wood_block', '037_scissors', '040_large_marker', \
                         '051_large_clamp', '052_extra_large_clamp', '061_foam_brick')

        self._class_colors = [(255, 255, 255), (255, 0, 0), (0, 255, 0), (0, 0, 255), (255, 255, 0), (255, 0, 255), (0, 255, 255), \
                              (128, 0, 0), (0, 128, 0), (0, 0, 128), (128, 128, 0), (128, 0, 128), (0, 128, 128), \
                              (64, 0, 0), (0, 64, 0), (0, 0, 64), (64, 64, 0), (64, 0, 64), (0, 64, 64), 
                              (192, 0, 0), (0, 192, 0), (0, 0, 192)]

        self._class_weights = [1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1, 1]
        self._symmetry = np.array([0, 1, 0, 0, 1, 0, 1, 0, 0, 0, 0, 0, 0, 1, 0, 0, 1, 0, 1, 0, 0, 1])
        self._points, self._points_all = self._load_object_points()
        self._extents = self._load_object_extents()

        self._class_to_ind = dict(zip(self.classes, xrange(self.num_classes)))
        self._image_ext = '.png'
        self._image_index = self._load_image_set_index()
        self._roidb_handler = self.gt_roidb

        assert os.path.exists(self._lov_path), \
                'lov path does not exist: {}'.format(self._lov_path)
        assert os.path.exists(self._data_path), \
                'Data path does not exist: {}'.format(self._data_path)

    # image
    def image_path_at(self, i):
        """
        Return the absolute path to image i in the image sequence.
        """
        return self.image_path_from_index(self.image_index[i])

    def image_path_from_index(self, index):
        """
        Construct an image path from the image's "index" identifier.
        """

        image_path = os.path.join(self._data_path, index + '-color' + self._image_ext)
        assert os.path.exists(image_path), \
                'Path does not exist: {}'.format(image_path)
        return image_path

    # depth
    def depth_path_at(self, i):
        """
        Return the absolute path to depth i in the image sequence.
        """
        return self.depth_path_from_index(self.image_index[i])

    def depth_path_from_index(self, index):
        """
        Construct an depth path from the image's "index" identifier.
        """
        depth_path = os.path.join(self._data_path, index + '-depth' + self._image_ext)
        assert os.path.exists(depth_path), \
                'Path does not exist: {}'.format(depth_path)
        return depth_path

    # label
    def label_path_at(self, i):
        """
        Return the absolute path to metadata i in the image sequence.
        """
        return self.label_path_from_index(self.image_index[i])

    def label_path_from_index(self, index):
        """
        Construct an metadata path from the image's "index" identifier.
        """
        label_path = os.path.join(self._data_path, index + '-label' + self._image_ext)
        assert os.path.exists(label_path), \
                'Path does not exist: {}'.format(label_path)
        return label_path

    # camera pose
    def metadata_path_at(self, i):
        """
        Return the absolute path to metadata i in the image sequence.
        """
        return self.metadata_path_from_index(self.image_index[i])

    def metadata_path_from_index(self, index):
        """
        Construct an metadata path from the image's "index" identifier.
        """
        metadata_path = os.path.join(self._data_path, index + '-meta.mat')
        assert os.path.exists(metadata_path), \
                'Path does not exist: {}'.format(metadata_path)
        return metadata_path

    def _load_image_set_index(self):
        """
        Load the indexes listed in this dataset's image set file.
        """
        image_set_file = os.path.join(self._lov_path, self._image_set + '.txt')
        assert os.path.exists(image_set_file), \
                'Path does not exist: {}'.format(image_set_file)

        with open(image_set_file) as f:
            image_index = [x.rstrip('\n') for x in f.readlines()]
        return image_index

    def _get_default_path(self):
        """
        Return the default path where KITTI is expected to be installed.
        """
        return os.path.join(datasets.ROOT_DIR, 'data', 'LOV')


    def _load_object_points(self):

        points = [[] for _ in xrange(len(self._classes))]
        num = np.inf

        for i in xrange(1, len(self._classes)):
            point_file = os.path.join(self._lov_path, 'models', self._classes[i], 'points.xyz')
            print point_file
            assert os.path.exists(point_file), 'Path does not exist: {}'.format(point_file)
            points[i] = np.loadtxt(point_file)
            if points[i].shape[0] < num:
                num = points[i].shape[0]

        points_all = np.zeros((self.num_classes, num, 3), dtype=np.float32)
        for i in xrange(1, len(self._classes)):
            points_all[i, :, :] = points[i][:num, :]

        return points, points_all


    def _load_object_extents(self):

        extent_file = os.path.join(self._lov_path, 'extents.txt')
        assert os.path.exists(extent_file), \
                'Path does not exist: {}'.format(extent_file)

        extents = np.zeros((self.num_classes, 3), dtype=np.float32)
        extents[1:, :] = np.loadtxt(extent_file)

        return extents


    def compute_class_weights(self):

        print 'computing class weights'
        num_classes = self.num_classes
        count = np.zeros((num_classes,), dtype=np.int64)
        for index in self.image_index:
            # label path
            label_path = self.label_path_from_index(index)
            im = cv2.imread(label_path, cv2.IMREAD_UNCHANGED)
            for i in xrange(num_classes):
                I = np.where(im == i)
                count[i] += len(I[0])

        for i in xrange(num_classes):
            self._class_weights[i] = min(float(count[0]) / float(count[i]), 10.0)
            print self._classes[i], self._class_weights[i]


    def gt_roidb(self):
        """
        Return the database of ground-truth regions of interest.

        This function loads/saves from/to a cache file to speed up future calls.
        """

        cache_file = os.path.join(self.cache_path, self.name + '_gt_roidb.pkl')
        if os.path.exists(cache_file):
            with open(cache_file, 'rb') as fid:
                roidb = cPickle.load(fid)
            print '{} gt roidb loaded from {}'.format(self.name, cache_file)
            print 'class weights: ', roidb[0]['class_weights']
            return roidb

        # self.compute_class_weights()

        gt_roidb = [self._load_lov_annotation(index)
                    for index in self.image_index]

        with open(cache_file, 'wb') as fid:
            cPickle.dump(gt_roidb, fid, cPickle.HIGHEST_PROTOCOL)
        print 'wrote gt roidb to {}'.format(cache_file)

        return gt_roidb


    def _load_lov_annotation(self, index):
        """
        Load class name and meta data
        """
        # image path
        image_path = self.image_path_from_index(index)

        # depth path
        depth_path = self.depth_path_from_index(index)

        # label path
        label_path = self.label_path_from_index(index)

        # metadata path
        metadata_path = self.metadata_path_from_index(index)

        # parse image name
        pos = index.find('/')
        video_id = index[:pos]

        # read boxes
        filename = os.path.join(self._data_path, index + '-box.txt')
        lines = []
        with open(filename) as f:
            for line in f:
                lines.append(line)

        num_objs = len(lines)
        boxes = np.zeros((num_objs, 4), dtype=np.float32)
        gt_classes = np.zeros((num_objs), dtype=np.int32)

        for ix, line in enumerate(lines):
            words = line.split()
            cls = self._class_to_ind[words[0]]
            boxes[ix, :] = [float(n) for n in words[1:5]]
            gt_classes[ix] = cls
        
        return {'image': image_path,
                'depth': depth_path,
                'label': label_path,
                'meta_data': metadata_path,
                'video_id': video_id,
                'class_colors': self._class_colors,
                'class_weights': self._class_weights,
                'boxes': boxes,
                'gt_classes': gt_classes,
                'flipped': False}

    def _process_label_image(self, label_image):
        """
        change label image to label index
        """
        class_colors = self._class_colors
        width = label_image.shape[1]
        height = label_image.shape[0]
        label_index = np.zeros((height, width), dtype=np.float32)

        # label image is in BGR order
        index = label_image[:,:,2] + 256*label_image[:,:,1] + 256*256*label_image[:,:,0]
        for i in xrange(len(class_colors)):
            color = class_colors[i]
            ind = color[0] + 256*color[1] + 256*256*color[2]
            I = np.where(index == ind)
            label_index[I] = i

        return label_index


    def labels_to_image(self, im, labels):
        class_colors = self._class_colors
        height = labels.shape[0]
        width = labels.shape[1]
        image_r = np.zeros((height, width), dtype=np.float32)
        image_g = np.zeros((height, width), dtype=np.float32)
        image_b = np.zeros((height, width), dtype=np.float32)

        for i in xrange(len(class_colors)):
            color = class_colors[i]
            I = np.where(labels == i)
            image_r[I] = color[0]
            image_g[I] = color[1]
            image_b[I] = color[2]

        image = np.stack((image_r, image_g, image_b), axis=-1)

        return image.astype(np.uint8)


    def evaluate_result(self, im_ind, segmentation, gt_labels, meta_data, output_dir):

        # make matlab result dir
        import scipy.io
        mat_dir = os.path.join(output_dir, 'mat')
        if not os.path.exists(mat_dir):
            os.makedirs(mat_dir)

        # evaluate segmentation
        n_cl = self.num_classes
        hist = np.zeros((n_cl, n_cl))

        gt_labels = gt_labels.astype(np.float32)
        sg_labels = segmentation['labels']
        hist += self.fast_hist(gt_labels.flatten(), sg_labels.flatten(), n_cl)

        # per-class IU
        print 'per-class segmentation IoU'
        intersection = np.diag(hist)
        union = hist.sum(1) + hist.sum(0) - np.diag(hist)
        index = np.where(union > 0)[0]
        for i in range(len(index)):
            ind = index[i]
            print '{} {}'.format(self._classes[ind], intersection[ind] / union[ind])

        # evaluate pose
        if cfg.TEST.POSE_REG:
            rois = segmentation['rois']
            poses = segmentation['poses']
            poses_new = segmentation['poses_refined']
            poses_icp = segmentation['poses_icp']

            # save matlab result
            results = {'labels': sg_labels, 'rois': rois, 'poses': poses, 'poses_refined': poses_new, 'poses_icp': poses_icp}
            filename = os.path.join(mat_dir, '%04d.mat' % im_ind)
            print filename
            scipy.io.savemat(filename, results, do_compression=True)

            poses_gt = meta_data['poses']
            if len(poses_gt.shape) == 2:
                poses_gt = np.reshape(poses_gt, (3, 4, 1))
            num = poses_gt.shape[2]

            for j in xrange(num):
                if meta_data['cls_indexes'][j] <= 0:
                    continue
                cls = self.classes[int(meta_data['cls_indexes'][j])]
                print cls
                print 'gt pose'
                print poses_gt[:, :, j]

                for k in xrange(rois.shape[0]):
                    cls_index = int(rois[k, 1])
                    if cls_index == meta_data['cls_indexes'][j]:

                        print 'estimated pose'
                        RT = np.zeros((3, 4), dtype=np.float32)
                        RT[:3, :3] = quat2mat(poses[k, :4])
                        RT[:, 3] = poses[k, 4:7]
                        print RT

                        if cfg.TEST.POSE_REFINE:
                            print 'translation refined pose'
                            RT_new = np.zeros((3, 4), dtype=np.float32)
                            RT_new[:3, :3] = quat2mat(poses_new[k, :4])
                            RT_new[:, 3] = poses_new[k, 4:7]
                            print RT_new

                            print 'ICP refined pose'
                            RT_icp = np.zeros((3, 4), dtype=np.float32)
                            RT_icp[:3, :3] = quat2mat(poses_icp[k, :4])
                            RT_icp[:, 3] = poses_icp[k, 4:7]
                            print RT_icp

                        error_rotation = re(RT[:3, :3], poses_gt[:3, :3, j])
                        print 'rotation error: {}'.format(error_rotation)

                        error_translation = te(RT[:, 3], poses_gt[:, 3, j])
                        print 'translation error: {}'.format(error_translation)

                        # compute pose error
                        if cls == '024_bowl' or cls == '036_wood_block' or cls == '061_foam_brick':
                            error = adi(RT[:3, :3], RT[:, 3], poses_gt[:3, :3, j], poses_gt[:, 3, j], self._points[cls_index])
                        else:
                            error = add(RT[:3, :3], RT[:, 3], poses_gt[:3, :3, j], poses_gt[:, 3, j], self._points[cls_index])
                        print 'error: {}'.format(error)

                        if cfg.TEST.POSE_REFINE:
                            error_rotation_new = re(RT_new[:3, :3], poses_gt[:3, :3, j])
                            print 'rotation error new: {}'.format(error_rotation_new)

                            error_translation_new = te(RT_new[:, 3], poses_gt[:, 3, j])
                            print 'translation error new: {}'.format(error_translation_new)

                            if cls == '024_bowl' or cls == '036_wood_block' or cls == '061_foam_brick':
                                error_new = adi(RT_new[:3, :3], RT_new[:, 3], poses_gt[:3, :3, j], poses_gt[:, 3, j], self._points[cls_index])
                            else:
                                error_new = add(RT_new[:3, :3], RT_new[:, 3], poses_gt[:3, :3, j], poses_gt[:, 3, j], self._points[cls_index])
                            print 'error new: {}'.format(error_new)

                            error_rotation_icp = re(RT_icp[:3, :3], poses_gt[:3, :3, j])
                            print 'rotation error icp: {}'.format(error_rotation_icp)

                            error_translation_icp = te(RT_icp[:, 3], poses_gt[:, 3, j])
                            print 'translation error icp: {}'.format(error_translation_icp)

                            if cls == '024_bowl' or cls == '036_wood_block' or cls == '061_foam_brick':
                                error_icp = adi(RT_icp[:3, :3], RT_icp[:, 3], poses_gt[:3, :3, j], poses_gt[:, 3, j], self._points[cls_index])
                            else:
                                error_icp = add(RT_icp[:3, :3], RT_icp[:, 3], poses_gt[:3, :3, j], poses_gt[:, 3, j], self._points[cls_index])
                            print 'error icp: {}'.format(error_icp)

                        print 'threshold: {}'.format(0.1 * np.linalg.norm(self._extents[cls_index, :]))
        

    def evaluate_segmentations(self, segmentations, output_dir):
        print 'evaluating segmentations'
        # compute histogram
        n_cl = self.num_classes
        hist = np.zeros((n_cl, n_cl))

        # make image dir
        image_dir = os.path.join(output_dir, 'images')
        if not os.path.exists(image_dir):
            os.makedirs(image_dir)

        # make matlab result dir
        import scipy.io
        mat_dir = os.path.join(output_dir, 'mat')
        if not os.path.exists(mat_dir):
            os.makedirs(mat_dir)

        count_all = np.zeros((self.num_classes,), dtype=np.float32)
        count_correct = np.zeros((self.num_classes,), dtype=np.float32)
        count_correct_refined = np.zeros((self.num_classes,), dtype=np.float32)
        count_correct_icp = np.zeros((self.num_classes,), dtype=np.float32)
        threshold = np.zeros((self.num_classes,), dtype=np.float32)
        for i in xrange(self.num_classes):
            threshold[i] = 0.1 * np.linalg.norm(self._extents[i, :])

        # for each image
        for im_ind, index in enumerate(self.image_index):
            # read ground truth labels
            im = cv2.imread(self.label_path_from_index(index), cv2.IMREAD_UNCHANGED)
            gt_labels = im.astype(np.float32)

            # predicated labels
            sg_labels = segmentations[im_ind]['labels']
            hist += self.fast_hist(gt_labels.flatten(), sg_labels.flatten(), n_cl)

            # evaluate pose
            if cfg.TEST.POSE_REG:
                # load meta data
                meta_data = scipy.io.loadmat(self.metadata_path_from_index(index))
            
                rois = segmentations[im_ind]['rois']
                poses = segmentations[im_ind]['poses']
                poses_new = segmentations[im_ind]['poses_refined']
                poses_icp = segmentations[im_ind]['poses_icp']

                '''
                # save matlab result
                results = {'labels': sg_labels, 'rois': rois, 'poses': poses, 'poses_refined': poses_new, 'poses_icp': poses_icp}
                filename = os.path.join(mat_dir, '%04d.mat' % im_ind)
                print filename
                scipy.io.savemat(filename, results, do_compression=True)
                '''

                poses_gt = meta_data['poses']
                if len(poses_gt.shape) == 2:
                    poses_gt = np.reshape(poses_gt, (3, 4, 1))
                num = poses_gt.shape[2]

                for j in xrange(num):
                    if meta_data['cls_indexes'][j] <= 0:
                        continue
                    cls = self.classes[int(meta_data['cls_indexes'][j])]
                    count_all[int(meta_data['cls_indexes'][j])] += 1
    
                    for k in xrange(rois.shape[0]):
                        cls_index = int(rois[k, 1])
                        if cls_index == meta_data['cls_indexes'][j]:

                            RT = np.zeros((3, 4), dtype=np.float32)
                            RT[:3, :3] = quat2mat(poses[k, :4])
                            RT[:, 3] = poses[k, 4:7]

                            if cfg.TEST.POSE_REFINE:
                                RT_new = np.zeros((3, 4), dtype=np.float32)
                                RT_new[:3, :3] = quat2mat(poses_new[k, :4])
                                RT_new[:, 3] = poses_new[k, 4:7]

                                RT_icp = np.zeros((3, 4), dtype=np.float32)
                                RT_icp[:3, :3] = quat2mat(poses_icp[k, :4])
                                RT_icp[:, 3] = poses_icp[k, 4:7]

                            error_rotation = re(RT[:3, :3], poses_gt[:3, :3, j])
                            error_translation = te(RT[:, 3], poses_gt[:, 3, j])
                            if cls == '024_bowl' or cls == '036_wood_block' or cls == '061_foam_brick':
                                error = adi(RT[:3, :3], RT[:, 3], poses_gt[:3, :3, j], poses_gt[:, 3, j], self._points[cls_index])
                            else:
                                error = add(RT[:3, :3], RT[:, 3], poses_gt[:3, :3, j], poses_gt[:, 3, j], self._points[cls_index])

                            if error < threshold[cls_index]:
                                count_correct[cls_index] += 1

                            if cfg.TEST.POSE_REFINE:
                                error_rotation_new = re(RT_new[:3, :3], poses_gt[:3, :3, j])
                                error_translation_new = te(RT_new[:, 3], poses_gt[:, 3, j])
                                if cls == '024_bowl' or cls == '036_wood_block' or cls == '061_foam_brick':
                                    error_new = adi(RT_new[:3, :3], RT_new[:, 3], poses_gt[:3, :3, j], poses_gt[:, 3, j], self._points[cls_index])
                                else:
                                    error_new = add(RT_new[:3, :3], RT_new[:, 3], poses_gt[:3, :3, j], poses_gt[:, 3, j], self._points[cls_index])

                                if error_new < threshold[cls_index]:
                                    count_correct_refined[cls_index] += 1

                                error_rotation_icp = re(RT_icp[:3, :3], poses_gt[:3, :3, j])
                                error_translation_icp = te(RT_icp[:, 3], poses_gt[:, 3, j])
                                if cls == '024_bowl' or cls == '036_wood_block' or cls == '061_foam_brick':
                                    error_icp = adi(RT_icp[:3, :3], RT_icp[:, 3], poses_gt[:3, :3, j], poses_gt[:, 3, j], self._points[cls_index])
                                else:
                                    error_icp = add(RT_icp[:3, :3], RT_icp[:, 3], poses_gt[:3, :3, j], poses_gt[:, 3, j], self._points[cls_index])

                                if error_icp < threshold[cls_index]:
                                    count_correct_icp[cls_index] += 1

            '''
            # label image
            rgba = cv2.imread(self.image_path_from_index(index), cv2.IMREAD_UNCHANGED)
            image = rgba[:,:,:3]
            alpha = rgba[:,:,3]
            I = np.where(alpha == 0)
            image[I[0], I[1], :] = 255
            label_image = self.labels_to_image(image, sg_labels)

            # save image
            filename = os.path.join(image_dir, '%04d.png' % im_ind)
            print filename
            cv2.imwrite(filename, label_image)
            '''

        # overall accuracy
        acc = np.diag(hist).sum() / hist.sum()
        print 'overall accuracy', acc
        # per-class accuracy
        acc = np.diag(hist) / hist.sum(1)
        print 'mean accuracy', np.nanmean(acc)
        # per-class IU
        print 'per-class IU'
        iu = np.diag(hist) / (hist.sum(1) + hist.sum(0) - np.diag(hist))
        for i in range(n_cl):
            print '{} {}'.format(self._classes[i], iu[i])
        print 'mean IU', np.nanmean(iu)
        freq = hist.sum(1) / hist.sum()
        print 'fwavacc', (freq[freq > 0] * iu[freq > 0]).sum()

        filename = os.path.join(output_dir, 'segmentation.txt')
        with open(filename, 'wt') as f:
            for i in range(n_cl):
                f.write('{:f}\n'.format(iu[i]))

        filename = os.path.join(output_dir, 'confusion_matrix.txt')
        with open(filename, 'wt') as f:
            for i in range(n_cl):
                for j in range(n_cl):
                    f.write('{:f} '.format(hist[i, j]))
                f.write('\n')

        # pose accuracy
        if cfg.TEST.POSE_REG:
            for i in xrange(1, self.num_classes):
                print '{} correct poses: {}, all poses: {}, accuracy: {}'.format(self.classes[i], count_correct[i], count_all[i], float(count_correct[i]) / float(count_all[i]))
                if cfg.TEST.POSE_REFINE:
                    print '{} correct poses after refinement: {}, all poses: {}, accuracy: {}'.format( \
                        self.classes[i], count_correct_refined[i], count_all[i], float(count_correct_refined[i]) / float(count_all[i]))
                    print '{} correct poses after ICP: {}, all poses: {}, accuracy: {}'.format( \
                        self.classes[i], count_correct_icp[i], count_all[i], float(count_correct_icp[i]) / float(count_all[i]))


if __name__ == '__main__':
    d = datasets.lov('train')
    res = d.roidb
    from IPython import embed; embed()
