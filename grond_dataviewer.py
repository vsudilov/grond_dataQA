import Tkinter as tk       
from PIL import Image, ImageTk
import os
import sys
import sqlite3
import pyfits
from multiprocessing import Pool
import uuid
import re
import argparse

BASEDIR = os.path.abspath(os.path.dirname(__file__))
sys.path.insert(0,BASEDIR)
from lib import astImages

DEBUG = False

DATABASE = os.path.join(BASEDIR,'dataviewer.db')
CACHE_DIR = os.path.join(BASEDIR,'cache')
FITS_REGEX = 'GROND_._OB_ana.fits'
IMAGE_ENGINE = astImages.saveBitmap
PLACEHOLDER_PNG = os.path.join(BASEDIR,'images/placeholder.png')
BANDS = 'grizJHK'

FLAGS = {
  'flag_guiding':         'Significant guiding problems',
  'flag_focus':           'Focus problems',
  'flag_ROnoise':         'Electronic readout noise problems',
  'flag_missingImage':    'One or more images missing',
  'flag_unknownErr':      'Some major unknown error has occured',
}

def initdb():
  db = sqlite3.connect(DATABASE)
  SQL = '''
        CREATE TABLE Flags (id INTEGER PRIMARY KEY AUTOINCREMENT, target TEXT, comments TEXT, viewed INTEGER, %s);
        '''
  SQL = SQL.strip()
  SQL = SQL % (','.join(FLAGS.keys()),)
  if DEBUG:
    print "initdb: SQL:\n %s" % SQL
  db.execute(SQL)
  db.commit()
  db.close()
  

class Application(tk.Frame):
  '''
  Creates the GROND data QA app.
  Loops (recursively) over the GROND_._OB_ana.fits images found in the CL specified
  path.
  Makes PNGs of the entire field, and presents them on a TKinter GUI. Saves the "flags"
  checkboxes to a sqlite3 database
  '''

  def __init__(self, args, master=None):
    self.args = args
    self.connectToDB()
    self.initTargets()
    self.initImages()
    tk.Frame.__init__(self, master)   
    self.grid()
    self.createWidgets()

  def initTargets(self):
    self.targets = []
    SQL = 'SELECT target FROM Flags'
    #if self.args.resume: #Not yet implemented
    #  SQL+= ' WHERE viewed==0'
    previous_targets = [i[0] for i in self.db.execute(SQL).fetchall()]
    if DEBUG:
      print "Walking directory structure to find GROND images. This may take a moment!"
    for path, dirs, files in os.walk(sys.argv[1]):
      for f in files:
        if re.search(FITS_REGEX,f):
          img = os.path.join(os.path.abspath(path),f)
          target = img[:re.search(FITS_REGEX,img).start()-2]
          if target not in self.targets:
            self.targets.append(target)
            if target not in previous_targets:
              SQL = '''
                    INSERT INTO Flags (target, comments, viewed, %s) VALUES (%s, NULL, 0, %s) 
                    '''
              SQL = SQL.strip()
              SQL = SQL % (','.join(FLAGS.keys()), '"%s"' % target, ','.join(["0" for i in range(len(FLAGS.keys()))]) )
              if DEBUG:
                print "initTarget with SQL:\n%s" % SQL
              self.db.execute(SQL)
              self.db.commit()
    self.current_target = self.targets[0]

  def initImages(self):
    '''
    Finds all GROND_._OB_ana.fits files in the CL specified directory
    Gives these images to the (async) process that creates the PNGs 
    '''
    pool = Pool(processes=5) 
    self.cache={}
    fitsimages = []
    for target in self.targets:
      for band in BANDS:
        img = os.path.join(target,'%s/GROND_%s_OB_ana.fits' % (band,band))
        if os.path.isfile(img):
          fitsimages.append(img)
    for image in fitsimages:
      if IMAGE_ENGINE==astImages.saveBitmap:
       d = pyfits.open(image)[0].data
       fname = os.path.join(CACHE_DIR,'%s.png' % uuid.uuid4())
       #saveBitmap(outputFileName, imageData, cutLevels, size, colorMapName)
       #cutLevels=["smart", 99.5],size=300,colorMapName='gray'
       args = [fname,image,d,["smart", 99.5],300,'gray_r']
      #if IMAGE_ENGINE==lib.ds9: #Not yet implemented
      #  args = []
      if DEBUG:
        print "Running asnyc job with args=%s" % args
      loadvalue = float(fitsimages.index(image))/len(fitsimages)*100.0
      if not round(loadvalue) % 10:
        print "Loading: %0.1f%%" % (loadvalue)
      pool.apply_async(IMAGE_ENGINE,args,callback=self.updateCache)
      #pool.apply(IMAGE_ENGINE,args)

  def updateCache(self,*args):
    image = args[0][0]
    fname = args[0][1]
    '''
    Callback function that is called whenever an async task completes.
    Updates the internal cache with {FITS_path:PNG_path}
    '''
    if DEBUG:
      print "updating cache with %s=%s" % (image,fname)
    self.cache[image]=fname

  def connectToDB(self):
    if not os.path.isfile(DATABASE):
      initdb()
    self.db = sqlite3.connect(DATABASE)

  def getImagesFromCache(self):
    '''
    Looks into the internal cache for PNGs. If not there, returns a placeholder image
    '''
    L = []
    for band in BANDS:
      ct = self.current_target
      ci = os.path.join(ct,'%s/GROND_%s_OB_ana.fits' % (band,band))
      if ci in self.cache.keys():
        L.append(self.cache[ci])
      else:
        L.append(PLACEHOLDER_PNG)
    return L #List of PNG paths  
      

  def printPosition(self,widget):
    '''
    Print the TKinter grid position (debug purposes only)
    '''
    grid_info = widget.grid_info()
    print "row:", grid_info["row"], "column:", grid_info["column"] 

  def refresh(self):
    self.clear()
    self.createWidgets()

  def clear(self):
    [i.grid_forget() for i in self.imlabels]
    [b.grid_forget() for b in self.buttons]
    [c.grid_forget() for c in self.checkboxes]
    [l.grid_forget() for l in self.labels]

  def save(self):
    '''
    Saves current info into the database
    '''
    
    SQL = '''  UPDATE Flags SET viewed=1 WHERE target=="%s"; ''' % self.current_target
    SQL = SQL.strip()
    for k,v in self.flags.iteritems():
      SQL+='UPDATE Flags SET %s=%s WHERE target=="%s";' % (k,v.get(),self.current_target)
    if DEBUG:
      print "save with SQL:\n%s" % SQL
    self.db.executescript(SQL)
    self.db.commit()
      

  def quit(self):
    self.save()
    if DEBUG:
      print "Cleanup: Removing all PNGs in %s" % CACHE_DIR
    os.system('rm %s/*png' % CACHE_DIR)
    #super(Application,self).quit() #tk.Frame is old-style class, super() won't work!
    tk.Frame.quit(self)

  def next(self):
    self.save()
    try:
      self.current_target = self.targets[self.targets.index(self.current_target)+1]
    except IndexError:
      print "\n---> Done.\n"
      self.quit()   
    self.clear()
    self.createWidgets()

  def createWidgets(self):
    self.imlabels = []
    col,row = 0,0
    span = 3
    for image in self.getImagesFromCache():
      photo = ImageTk.PhotoImage(Image.open(image))
      imlabel = tk.Label(self,image=photo)
      imlabel.image = photo # keep a reference!
      imlabel.grid(column=col,row=row,columnspan=span,rowspan=span,stick=tk.W+tk.E+tk.S+tk.N)
      col += 1*span
      if col > 2*span:
        row += 1*span
        col = 0
      self.imlabels.append(imlabel)

    self.buttons = []
    self.checkboxes = []
    self.labels = []
    startcol = col
    self.flags = {}
    for k,v in FLAGS.iteritems():
      self.flags[k] = tk.IntVar()
      c = tk.Checkbutton(self,text=v,variable=self.flags[k])
      c.grid(column=col,row=row)
      col+=1
      if col>2*span:
        row+=1
        col = startcol
      self.checkboxes.append(c)

    #buttons = { 'Save and quit':self.quit,
    #            'Save and continue':self.next,
    #            'Refresh page':self.refresh,
    #            'Previous':self.back,
    #           } 
    #Better to set buttons manually -- easier to set grid() position
    
    b = tk.Button(self, text='Save and Quit', command=self.quit)
    b.grid(column=100,row=0)        
    self.buttons.append(b)

    b = tk.Button(self, text="Save and continue",command=self.next)
    b.grid(column=100,row=100)
    self.buttons.append(b)
    
    b = tk.Button(self, text="Refresh page",command=self.refresh)
    b.grid()
    self.buttons.append(b)

#    b = tk.Button(self, text="Previous",command=self.back)
#    b.grid(column=99,row=100)
#    self.buttons.append(b)
    
    text = "%s (%s/%s)" % (self.current_target,self.targets.index(self.current_target)+1,len(self.targets))
    l = tk.Label(self,text=text)
    l.grid(column=50,row=100)
    self.labels.append(l)

    SQL = 'SELECT viewed FROM Flags WHERE target=="%s"' % self.current_target
    result = self.db.execute(SQL).fetchall()[0][0]
    if result:
      print self.current_target,result
      text = "This target has been viewed at least once before"
      l = tk.Label(self,text=text,fg="blue")
      l.grid(column=1,row=100,columnspan=5,sticky=tk.W)
      self.labels.append(l)
  

    if DEBUG:
      print "Images:"
      [self.printPosition(i) for i in self.imlabels]
      print "Buttons:"
      [self.printPosition(b) for b in self.buttons]



if __name__ == "__main__":
  parser = argparse.ArgumentParser()
  parser.add_argument('PATH',nargs=1)
  #parser.add_argument('--resume', dest='resume',default=False,action="store_true") #Not yet implemented
  args = parser.parse_args()
  if DEBUG:
    print args
  app = Application(args)                       
  app.master.title('Title')    
  app.mainloop()          
                  
