#!/usr/bin/python

# find our custom built opencv first
import sys
sys.path.insert(0, "/usr/local/opencv-2.4.11/lib/python2.7/site-packages/")

import argparse
import cv2
import math
import numpy as np

d2r = math.pi / 180.0

match_ratio = 0.6
max_features = 500
smooth = 0.001
catchup = 0.05
affine_minpts = 15
fundamental_tol = 2.0

parser = argparse.ArgumentParser(description='Estimate gyro biases from movie.')
parser.add_argument('--movie', required=True, help='movie file')
parser.add_argument('--scale', type=float, default=1.0, help='scale input')
parser.add_argument('--skip-frames', type=int, default=0, help='skip n initial frames')
parser.add_argument('--draw-masks', action='store_true', help='draw stabilization masks')
args = parser.parse_args()

file = args.movie
scale = args.scale
skip_frames = args.skip_frames

try:
    print "Opening ", args.movie
    #capture = cv2.VideoCapture("video.avi")
    #capture = cv2.VideoCapture("/home/curt/Dropbox/FRAM/VID_20141106_131255.mp4")
    capture = cv2.VideoCapture(args.movie)
    #capture = cv2.VideoCapture()
except:
    print "error opening video"

print "ok opening video"
capture.read()
print "ok reading first frame"

fps = capture.get(cv2.cv.CV_CAP_PROP_FPS)
print "fps = %.2f" % fps
fourcc = int(capture.get(cv2.cv.CV_CAP_PROP_FOURCC))
w = int(capture.get(cv2.cv.CV_CAP_PROP_FRAME_WIDTH) * scale )
h = int(capture.get(cv2.cv.CV_CAP_PROP_FRAME_HEIGHT) * scale )

#outfourcc = cv2.cv.CV_FOURCC('F', 'M', 'P', '4')
outfourcc = cv2.cv.CV_FOURCC('M', 'J', 'P', 'G')
#outfourcc = cv2.cv.CV_FOURCC('X', 'V', 'I', 'D')
#outfourcc = cv2.VideoWriter_fourcc(*'XVID')
output = cv2.VideoWriter("output.avi", outfourcc, fps, (w, h))

# find affine transform between matching keypoints in pixel
# coordinate space.  fullAffine=True means unconstrained to
# include best warp/shear.  fullAffine=False means limit the
# matrix to only best rotation, translation, and scale.
def findAffine(src, dst, fullAffine=False):
    #print "src = %s" % str(src)
    #print "dst = %s" % str(dst)
    if len(src) >= affine_minpts:
        affine = cv2.estimateRigidTransform(np.array([src]), np.array([dst]),
                                            fullAffine)
    else:
        affine = None
    #print str(affine)
    return affine

def decomposeAffine(affine):
    if affine == None:
        return (0.0, 0.0, 0.0, 1.0, 1.0)

    tx = affine[0][2]
    ty = affine[1][2]

    a = affine[0][0]
    b = affine[0][1]
    c = affine[1][0]
    d = affine[1][1]

    sx = math.sqrt( a*a + b*b )
    if a < 0.0:
        sx = -sx
    sy = math.sqrt( c*c + d*d )
    if d < 0.0:
        sy = -sy

    rotate_deg = math.atan2(-b,a) * 180.0/math.pi
    if rotate_deg < -180.0:
        rotate_deg += 360.0
    if rotate_deg > 180.0:
        rotate_deg -= 360.0
    return (rotate_deg, tx, ty, sx, sy)

def filterMatches(kp1, kp2, matches):
    mkp1, mkp2 = [], []
    idx_pairs = []
    used = np.zeros(len(kp2), np.bool_)
    for m in matches:
        if len(m) == 2 and m[0].distance < m[1].distance * match_ratio:
            #print " dist[0] = %d  dist[1] = %d" % (m[0].distance, m[1].distance)
            m = m[0]
            if not used[m.trainIdx]:
                used[m.trainIdx] = True
                mkp1.append( kp1[m.queryIdx] )
                mkp2.append( kp2[m.trainIdx] )
                idx_pairs.append( (m.queryIdx, m.trainIdx) )
    p1 = np.float32([kp.pt for kp in mkp1])
    p2 = np.float32([kp.pt for kp in mkp2])
    kp_pairs = zip(mkp1, mkp2)
    return p1, p2, kp_pairs, idx_pairs, mkp1

def filterByFundamental(p1, p2):
    inliers = 0
    total = len(p1)
    space = ""
    status = []
    while inliers < total and total >= 7:
        M, status = cv2.findFundamentalMat(p1, p2, cv2.RANSAC, fundamental_tol)
        newp1 = []
        newp2 = []
        for i, flag in enumerate(status):
            if flag:
                newp1.append(p1[i])
                newp2.append(p2[i])
        p1 = np.float32(newp1)
        p2 = np.float32(newp2)
        inliers = np.sum(status)
        total = len(status)
        #print '%s%d / %d  inliers/matched' % (space, np.sum(status), len(status))
        space += " "
    return status, p1, p2

def overlay(new_frame, base, motion_mask=None):
    newtmp = cv2.cvtColor(new_frame, cv2.COLOR_BGR2GRAY)
    ret, newmask = cv2.threshold(newtmp, 0, 255, cv2.THRESH_BINARY_INV)

    blendsize = (3,3)
    kernel = np.ones(blendsize,'uint8')
    mask_dilate = cv2.dilate(newmask, kernel)
    #cv2.imshow('mask_dilate', mask_dilate)
    ret, mask_final = cv2.threshold(mask_dilate, 254, 255, cv2.THRESH_BINARY)
    if args.draw_masks:
        cv2.imshow('mask_final', mask_final)

    mask_inv = 255 - mask_final
    if motion_mask != None:
        motion_inv = 255 - motion_mask
        mask_inv = cv2.bitwise_and(mask_inv, motion_mask)
        cv2.imshow('mask_inv1', mask_inv)
        mask_final = cv2.bitwise_or(mask_final, motion_inv)
        cv2.imshow('mask_final1', mask_final)
    if args.draw_masks:
        cv2.imshow('mask_inv', mask_inv)

    mask_final_norm = mask_final / 255.0
    mask_inv_norm = mask_inv / 255.0

    base[:,:,0] = base[:,:,0] * mask_final_norm
    base[:,:,1] = base[:,:,1] * mask_final_norm
    base[:,:,2] = base[:,:,2] * mask_final_norm
    #cv2.imshow('base', base)

    new_frame[:,:,0] = new_frame[:,:,0] * mask_inv_norm
    new_frame[:,:,1] = new_frame[:,:,1] * mask_inv_norm
    new_frame[:,:,2] = new_frame[:,:,2] * mask_inv_norm

    accum = cv2.add(base, new_frame)
    #cv2.imshow('accum', accum)
    return accum

def motion1(new_frame, base):
    motion = cv2.absdiff(base, new_frame)
    gray = cv2.cvtColor(motion, cv2.COLOR_BGR2GRAY)
    cv2.imshow('motion', gray)
    ret, motion_mask = cv2.threshold(gray, 25, 255, cv2.THRESH_BINARY_INV)

    blendsize = (3,3)
    kernel = np.ones(blendsize,'uint8')
    motion_mask = cv2.erode(motion_mask, kernel)

    # lots
    motion_mask /= 1.1429
    motion_mask += 16

    # medium
    #motion_mask /= 1.333
    #motion_mask += 32

    # minimal
    #motion_mask /= 2
    #motion_mask += 64

    cv2.imshow('motion1', motion_mask)
    return motion_mask

def motion2(new_frame, base):
    motion = cv2.absdiff(base, new_frame)
    gray = cv2.cvtColor(motion, cv2.COLOR_BGR2GRAY)
    cv2.imshow('motion', gray)
    motion_mask = 255 - gray
    motion_mask /= 2
    motion_mask += 2

    cv2.imshow('motion1', motion_mask)
    return motion_mask

detector = cv2.ORB(max_features)
norm = cv2.NORM_HAMMING
matcher = cv2.BFMatcher(norm)

accum = None
kp_list_last = []
des_list_last = []
p1 = []
p2 = []
mkp1 = []
counter = 0

rot_avg = 0.0
tx_avg = 0.0
ty_avg = 0.0
sx_avg = 1.0
sy_avg = 1.0

rot_sum = 0.0
tx_sum = 0.0
ty_sum = 0.0
sx_sum = 1.0
sy_sum = 1.0

# umn test
abs_rot = 0.0
abs_x = 0.0
abs_y = 0.0

result = []
stop_count = 0

while True:
    counter += 1

    filtered = []
    ret, frame = capture.read()

    if not ret:
        # no frame
        stop_count += 1
        print "no more frames:", stop_count
        if stop_count > 100:
            break

    if counter < skip_frames:
        if counter % 1000 == 0:
            print "Skipping %d frames..." % counter
        continue

    print "Frame %d" % counter

    if frame == None:
        print "Skipping bad frame ..."
        continue

    method = cv2.INTER_AREA
    #method = cv2.INTER_LANCZOS4
    frame = cv2.resize(frame, (0,0), fx=scale, fy=scale,
                     interpolation=method)

    # experimental undistortion
    K_Mobius_1080p = np.array( [[1446.47271782,    0.,         995.97981187],
                                [   0.,         1355.97161653, 660.86038277],
                                [   0.,            0.,           1.        ]] )

    K_720_16x9 = np.array([ [469.967, 0.0, 640],
                            [0.0, 467.682, 360],
                            [0.0, 0.0, 1.0] ] )
    # guessed from the 16x9 version
    K_720_3x4 = np.array([ [469.967, 0.0, 480],
                          [0.0, 467.682, 360],
                          [0.0, 0.0, 1.0] ] )

    K_960_3x4 = K_720_3x4 * (960.0 / 720.0)
    K_960_3x4[2:2] = 1.0

    K_1080_16x9 = K_720_16x9 * (1080.0 / 720.0)
    K_1080_16x9[2,2] = 1.0

    dist_mobius = [ -0.40697795,  0.22146696, -0.02121735, -0.00270626, -0.08839147 ]
    dist_gopro = [ -0.18957, 0.037319, 0.0, 0.0, -0.00337 ] # ???

    K = K_Mobius_1080p * args.scale
    K[2,2] = 1.0
    frame = cv2.undistort(frame, K, np.array(dist_mobius))
    cv2.imshow('undistort', frame)

    process_hsv = False
    if process_hsv:
        # Convert BGR to HSV
        hsv = cv2.cvtColor(frame, cv2.COLOR_BGR2HSV)
        hue,s,v = cv2.split(hsv)
        cv2.imshow('hue', hue)
        cv2.imshow('saturation', s)
        cv2.imshow('value', v)
        image = hue
    else:
        image = frame

    kp_list = detector.detect(image)
    kp_list, des_list = detector.compute(image, kp_list)

    if len(kp_list_last):
        matches = matcher.knnMatch(des_list, trainDescriptors=des_list_last, k=2)
        p1, p2, kp_pairs, idx_pairs, mkp1 = filterMatches(kp_list, kp_list_last, matches)

        # filtering by fundamental matrix would reject keypoints that
        # are not mathematically possible from one frame to the next
        # but in an anomaly detection scenerio at sea, we might only
        # have one match so this wouldn't work
        filter_fundamental = True
        if filter_fundamental:
            #print "before = ", len(p1)
            status, p1, p2 = filterByFundamental(p1, p2)
            filtered = []
            for i, flag in enumerate(status):
                if flag:
                    filtered.append(mkp1[i])
            #print "filtered = ", len(filtered)
        else:
            filtered = mkp1

    affine = findAffine(p2, p1, fullAffine=False)
    (rot, tx, ty, sx, sy) = decomposeAffine(affine)
    #print affine
    #print (rot, tx, ty, sx, sy)

    abs_rot += rot
    abs_rot *= 0.95
    abs_x += tx
    abs_x *= 0.95
    abs_y += ty
    abs_y *= 0.95
    
    print "motion: %d %.2f %.1f %.1f %.2f %.1f %.1f" % (counter, rot, tx, ty, abs_rot, abs_x, abs_y)

    translate_only = False
    rotate_translate_only = True
    if translate_only:
        rot = 0.0
        sx = 1.0
        sy = 1.0
    elif rotate_translate_only:
        sx = 1.0
        sy = 1.0

    # low pass filter our affine components
    keep = (1.0 - smooth)
    rot_avg = keep * rot_avg + smooth * rot
    tx_avg = keep * tx_avg + smooth * tx
    ty_avg = keep * ty_avg + smooth * ty
    sx_avg = keep * sx_avg + smooth * sx
    sy_avg = keep * sy_avg + smooth * sy
    print "%.2f %.2f %.2f %.4f %.4f" % (rot_avg, tx_avg, ty_avg, sx_avg, sy_avg)
    datapt = [ counter / fps, counter, -rot*fps*d2r, ty, tx ]
    result.append(datapt)
    
    # try to catch bad cases
    #if math.fabs(rot) > 5.0 * math.fabs(rot_avg) and \
    #   math.fabs(tx) > 5.0 * math.fabs(tx_avg) and \
    #   math.fabs(ty) > 5.0 * math.fabs(ty_avg) and \
    #   math.fabs(sx - 1.0) > 5.0 * math.fabs(sx_avg - 1.0) and \
    #   math.fabs(sy - 1.0) > 5.0 * math.fabs(sy_avg - 1.0):
    #    rot = 0.0
    #    tx = 0.0
    #    ty = 0.0
    #    sx = 1.0
    #    sy = 1.0

    # total transforms needed
    rot_sum += rot
    tx_sum += tx
    ty_sum += ty
    sx_sum += (sx - 1.0)
    sy_sum += (sy - 1.0)

    # save left overs
    rot_sum -= rot_avg
    tx_sum -= tx_avg
    ty_sum -= ty_avg
    sx_sum = (sx_sum - sx_avg) + 1.0
    sy_sum = (sy_sum - sy_avg) + 1.0

    # catch up on left overs
    rot_catchup = catchup * rot_sum; rot_sum -= rot_catchup
    tx_catchup = catchup * tx_sum; tx_sum -= tx_catchup
    ty_catchup = catchup * ty_sum; ty_sum -= ty_catchup
    sx_catchup = catchup * (sx_sum - 1.0); sx_sum -= sx_catchup
    sy_catchup = catchup * (sy_sum - 1.0); sy_sum -= sy_catchup

    rot_delta = (rot_avg + rot_catchup) - rot_sum
    tx_delta = (tx_avg + tx_catchup) - tx_sum
    ty_delta = (ty_avg + ty_catchup) - ty_sum
    sx_delta = (sx_avg + sx_catchup - sx_sum) + 1.0
    sy_delta = (sy_avg + sy_catchup - sy_sum) + 1.0

    rot_rad = rot_delta * math.pi / 180.0
    costhe = math.cos(rot_rad)
    sinthe = math.sin(rot_rad)
    row1 = [ sx_delta * costhe, -sx_delta * sinthe, tx_delta ]
    row2 = [ sy_delta * sinthe,  sy_delta * costhe, ty_delta ]
    affine_new = np.array( [ row1, row2 ] )
    # print affine_new

    #rot_last = -(rot_delta - rot)
    #tx_last = -(tx_delta - tx)
    #ty_last = -(ty_delta - ty)
    #sx_last = -(sx_delta - sx) + 1.0
    #sy_last = -(sy_delta - sy) + 1.0

    rot_last = (rot_avg + rot_catchup)
    tx_last = (tx_avg + tx_catchup)
    ty_last = (ty_avg + ty_catchup)
    sx_last = (sx_avg - 1.0 + sx_catchup) + 1.0
    sy_last = (sy_avg - 1.0 + sy_catchup) + 1.0

    rot_rad = rot_last * math.pi / 180.0
    costhe = math.cos(rot_rad)
    sinthe = math.sin(rot_rad)
    row1 = [ sx_last * costhe, -sx_last * sinthe, tx_last ]
    row2 = [ sy_last * sinthe,  sy_last * costhe, ty_last ]
    affine_last = np.array( [ row1, row2 ] )
    # print affine_new

    rows, cols, depth = frame.shape
    new_frame = cv2.warpAffine(frame, affine_new, (cols,rows))

    do_draw_keypoints = True
    if do_draw_keypoints:
        res1 = cv2.drawKeypoints(frame, filtered, color=(0,255,0), flags=0)
        #res2 = cv2.drawKeypoints(hue, filtered, color=(0,255,0), flags=0)
    else:
        res1 = frame

    kp_list_last = kp_list
    des_list_last = des_list

    # composite with history
    if accum == None:
        accum = new_frame
    else:
        base = cv2.warpAffine(accum, affine_last, (cols, rows))
        do_motion_fade = False
        if do_motion_fade:
            motion_mask = motion2(new_frame, base)
        else:
            motion_mask = None
        accum = overlay(new_frame, base, motion_mask)

    final = accum
    do_draw_keypoints_on_output = True
    if do_draw_keypoints_on_output:
        new_filtered = []
        if affine_new != None:
            affine_T = affine_new.T
            for kp in filtered:
                a = np.array( [kp.pt[0], kp.pt[1], 1.0] )
                pt = np.dot(a, affine_T)
                new_kp = cv2.KeyPoint(pt[0], pt[1], kp.size)
                new_filtered.append(new_kp)
        final = cv2.drawKeypoints(accum, new_filtered, color=(0,255,0), flags=0)
   
    cv2.imshow('bgr', res1)
    cv2.imshow('smooth', new_frame)
    cv2.imshow('final', final)
    output.write(final)
    if 0xFF & cv2.waitKey(5) == 27:
        break

cv2.destroyAllWindows()

with open('output.csv', 'wb') as myfile:
    for line in result:
        myfile.write(str(line[0]))
        for field in line[1:]:
            myfile.write('\t' + str(field))
        myfile.write('\n')